"""Market data: yfinance primary, deterministic mock fallback, TTL-cached.

yfinance is keyless, which is why it is primary. It is also an unofficial wrapper
over Yahoo endpoints, so it breaks when Yahoo changes shape and throttles by IP -
hence the pinned version, the aggressive TTL cache, and the labelled mock at the
end of the chain. A demo must never die because a third party rate-limited us.

The chain is: fresh cache -> live provider -> last-good stale cache -> mock.
Every result carries a DataStatus, and anything but LIVE must be disclosed.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import datetime, timezone

from src.core.cache import make_key
from src.core.contracts import DataStatus, Quote

_HUMAN = {"yfinance": "Yahoo Finance", "mock": "sample data", "alphavantage": "Alpha Vantage"}

# Stable base prices so the mock is deterministic per symbol per day.
_MOCK_BASE = {
    "AAPL": 232.0, "MSFT": 425.0, "NVDA": 139.0, "GOOGL": 178.0, "AMZN": 198.0, "META": 585.0,
    "TSLA": 248.0, "SPY": 580.0, "QQQ": 495.0, "VTI": 288.0, "VXUS": 62.0, "BND": 73.0,
    "VOO": 532.0, "IWM": 222.0, "AGG": 98.0, "BTC-USD": 62000.0, "ETH-USD": 2450.0,
    "SCHD": 82.0, "VNQ": 92.0, "TLT": 92.0,
}


def humanize_age(seconds: int) -> str:
    if seconds < 90:
        return "moments"
    if seconds < 5400:
        return f"{max(1, seconds // 60)} minutes"
    if seconds < 172800:
        return f"{max(1, seconds // 3600)} hours"
    return f"{seconds // 86400} days"


def build_notice(status: DataStatus, provider: str, age_seconds: int = 0) -> str | None:
    """LIVE returns None: silence means current. Everything else says so out loud."""
    label = _HUMAN.get(provider, provider)
    if status is DataStatus.LIVE:
        return None
    if status is DataStatus.CACHED:
        return f"Cached from {label}, about {humanize_age(age_seconds)} old. Not a fresh lookup."
    if status is DataStatus.STALE:
        return (f"{label} is unreachable, so this is the last known value, about "
                f"{humanize_age(age_seconds)} old.")
    return "Sample data, not real market data. Shown so the interface remains usable offline."


class MockProvider:
    """Deterministic synthetic quotes. Seeded by symbol+date so a demo recorded
    twice shows the same numbers. Never cached, so it can't be mistaken for real."""

    name = "mock"

    def supports(self, symbol: str) -> bool:
        return True

    def _price(self, symbol: str) -> float:
        sym = symbol.upper()
        rng = random.Random(f"{sym}:{datetime.now(timezone.utc).date()}")
        base = _MOCK_BASE.get(sym, 50.0 + (sum(map(ord, sym)) % 400))
        return round(base * (1 + rng.uniform(-0.02, 0.02)), 2)

    def quotes(self, symbols: Sequence[str]) -> list[Quote]:
        out = []
        for s in symbols:
            rng = random.Random(f"{s.upper()}:chg:{datetime.now(timezone.utc).date()}")
            out.append(Quote(symbol=s.upper(), price=self._price(s),
                             change_pct=round(rng.uniform(-2.2, 2.2), 2),
                             provider=self.name, status=DataStatus.SAMPLE,
                             as_of=datetime.now(timezone.utc),
                             notice=build_notice(DataStatus.SAMPLE, self.name)))
        return out

    def history(self, symbol: str, period: str = "6mo") -> list[tuple[str, float]]:
        rng = random.Random(f"{symbol.upper()}:hist")
        price = self._price(symbol) * 0.85
        out = []
        for i in range(126):
            price *= 1 + rng.uniform(-0.016, 0.018)
            out.append((f"d{i}", round(price, 2)))
        return out


class YFinanceProvider:
    """Quotes are derived from a short daily history rather than fast_info.

    yfinance 1.7 returns None from fast_info["last_price"] and yields a MultiIndex
    frame from download(), but Ticker.history() is reliable - so the last two closes
    give both the price and the daily change. Fewer moving parts, one code path
    shared with the chart data.
    """

    name = "yfinance"

    def supports(self, symbol: str) -> bool:
        return bool(symbol and len(symbol) <= 12)

    @staticmethod
    def _closes(symbol: str, period: str = "5d") -> list[tuple[str, float]]:
        import yfinance as yf

        df = yf.Ticker(symbol.upper()).history(period=period, interval="1d")
        if df is None or df.empty or "Close" not in df:
            return []
        # NaN closes are DROPPED, not passed on. yfinance returns them for
        # partial or holiday rows, and one of them poisons everything
        # downstream: a NaN price made the portfolio total render as "$nan",
        # every weight blank, and the diversification and risk scores read
        # 100/100. Worse, the bad quote was cached, so it kept doing it.
        #
        # Dropping here rather than at each call site because quotes(),
        # history(), the moving averages, volatility and the correlation
        # matrix all read through this one function.
        import math

        return [(str(idx.date()), round(float(c), 2))
                for idx, c in zip(df.index, df["Close"].tolist(), strict=False)
                if c is not None and math.isfinite(float(c))]

    def quotes(self, symbols: Sequence[str]) -> list[Quote]:
        out: list[Quote] = []
        for sym in symbols:
            closes = self._closes(sym)
            if not closes:
                continue
            price = closes[-1][1]
            prev = closes[-2][1] if len(closes) > 1 else None
            change = round(100.0 * (price - prev) / prev, 2) if prev else None
            out.append(Quote(symbol=sym.upper(), price=price, change_pct=change,
                             provider=self.name, status=DataStatus.LIVE,
                             as_of=datetime.now(timezone.utc)))
        if not out:
            raise RuntimeError("yfinance returned no usable quotes")
        return out

    def history(self, symbol: str, period: str = "6mo") -> list[tuple[str, float]]:
        rows = self._closes(symbol, period)
        if not rows:
            raise RuntimeError(f"no history for {symbol}")
        return rows


class MarketService:
    """Walks the provider chain, caching successes and labelling everything else."""

    def __init__(self, providers: Sequence, cache, *, quote_ttl: int = 1800,
                 history_ttl: int = 21600, stale_max_age: int = 604800) -> None:
        self._providers = list(providers)
        self._cache = cache
        self._quote_ttl = quote_ttl
        self._history_ttl = history_ttl
        self._stale_max = stale_max_age
        self.last_status: DataStatus = DataStatus.LIVE
        # last_status defaults to LIVE so callers have something to read, but on a
        # cold process nothing has actually been fetched. The nav paints a status
        # dot from this, and a green "live" dot that no provider earned is a lie -
        # so consumers must check `observed` before trusting last_status.
        self.observed: bool = False
        self.health: dict[str, str] = {}

    def quotes(self, symbols: Sequence[str]) -> dict[str, Quote]:
        wanted = [s.upper() for s in symbols if s]
        if not wanted:
            return {}
        self.observed = True
        key = make_key("market:quotes", ",".join(sorted(wanted)))

        fresh = self._cache.get(key, self._quote_ttl)
        if fresh:
            self.last_status = DataStatus.CACHED
            aged = self._cache.get_stale(key, self._stale_max)
            age = aged[1] if aged else 0
            return {q["symbol"]: Quote(**{**q, "status": DataStatus.CACHED,
                                          "notice": build_notice(DataStatus.CACHED, q.get("provider", ""), age)})
                    for q in fresh}

        for provider in self._providers:
            if provider.name == "mock":
                continue
            try:
                quotes = provider.quotes([s for s in wanted if provider.supports(s)])
            except Exception as exc:  # noqa: BLE001 - try the next provider
                self.health[provider.name] = f"error: {type(exc).__name__}"
                continue
            if quotes:
                self.health[provider.name] = "ok"
                self._cache.set(key, [q.model_dump(mode="json") for q in quotes])
                self.last_status = DataStatus.LIVE
                return {q.symbol: q for q in quotes}

        stale = self._cache.get_stale(key, self._stale_max)
        if stale:
            rows, age = stale
            self.last_status = DataStatus.STALE
            return {q["symbol"]: Quote(**{**q, "status": DataStatus.STALE,
                                          "notice": build_notice(DataStatus.STALE, q.get("provider", ""), age)})
                    for q in rows}

        self.last_status = DataStatus.SAMPLE
        return {q.symbol: q for q in MockProvider().quotes(wanted)}

    def history(self, symbol: str, period: str = "6mo") -> tuple[list[tuple[str, float]], DataStatus]:
        key = make_key("market:history", symbol.upper(), period)
        fresh = self._cache.get(key, self._history_ttl)
        if fresh:
            return [tuple(r) for r in fresh], DataStatus.CACHED
        for provider in self._providers:
            if provider.name == "mock":
                continue
            try:
                rows = provider.history(symbol, period)
            except Exception:  # noqa: BLE001
                continue
            if rows:
                self._cache.set(key, rows)
                return rows, DataStatus.LIVE
        stale = self._cache.get_stale(key, self._stale_max)
        if stale:
            return [tuple(r) for r in stale[0]], DataStatus.STALE
        return MockProvider().history(symbol, period), DataStatus.SAMPLE
