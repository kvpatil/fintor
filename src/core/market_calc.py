"""Market-series maths: pure functions, no I/O, no globals.

Same contract as `quant.py` — these take data and return data, which is what
makes them testable against hand-computed values rather than against themselves.
Code computes, the model explains (see the ai-grounding skill).

Every function raises on too-few points rather than returning a number that looks
plausible. A 2-point "volatility" is worse than an error, because it will be
narrated to a user as though it meant something.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

TRADING_DAYS = 252


class InsufficientData(ValueError):
    """Raised when a series is too short for the statistic to mean anything."""

    def __init__(self, needed: int, got: int, what: str) -> None:
        super().__init__(f"{what} needs at least {needed} points, got {got}")


def _check(series: Sequence[float], needed: int, what: str) -> None:
    if len(series) < needed:
        raise InsufficientData(needed, len(series), what)


def moving_average(series: Sequence[float], window: int) -> list[float | None]:
    """Simple moving average, aligned to the input.

    The first `window - 1` entries are None rather than back-filled: drawing a
    20-day average over the first 5 days would be a line the data cannot support.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    out: list[float | None] = []
    running = 0.0
    for i, value in enumerate(series):
        running += value
        if i >= window:
            running -= series[i - window]
        out.append(round(running / window, 4) if i >= window - 1 else None)
    return out


def rebase(series: Sequence[float], base: float = 100.0) -> list[float]:
    """Index a series so it starts at `base`.

    This is how two series of different magnitude get compared on ONE axis - the
    alternative, a second y-axis, is the most common charting mistake there is.
    """
    _check(series, 1, "rebase")
    first = series[0]
    if first == 0:
        raise ValueError("cannot rebase a series starting at zero")
    return [round(base * v / first, 4) for v in series]


def period_return(series: Sequence[float]) -> float:
    """Total percentage change across the series."""
    _check(series, 2, "period return")
    first, last = series[0], series[-1]
    if first == 0:
        raise ValueError("cannot compute a return from a zero start")
    return round(100.0 * (last - first) / first, 4)


def max_drawdown(series: Sequence[float]) -> float:
    """Largest peak-to-trough decline, as a positive percentage.

    Describes the worst experience of holding the asset over the window, which
    tends to predict investor behaviour better than volatility does.
    """
    _check(series, 2, "max drawdown")
    peak = series[0]
    worst = 0.0
    for value in series:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return round(100.0 * worst, 4)


def returns(series: Sequence[float]) -> list[float]:
    """Simple period-over-period returns."""
    _check(series, 2, "returns")
    out = []
    for prev, curr in zip(series, series[1:], strict=False):
        out.append((curr - prev) / prev if prev else 0.0)
    return out


def volatility(series: Sequence[float], periods_per_year: int = TRADING_DAYS) -> float:
    """Annualised standard deviation of returns, as a percentage."""
    _check(series, 10, "volatility")
    rets = returns(series)
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(100.0 * math.sqrt(variance) * math.sqrt(periods_per_year), 4)


def sharpe(annual_return_pct: float, annual_vol_pct: float,
           risk_free_pct: float = 0.0) -> float:
    """Return above the risk-free rate per unit of volatility.

    Penalises upside and downside volatility equally, which is the well-known
    limitation and the reason Sortino exists.
    """
    if annual_vol_pct <= 0:
        raise ValueError("Sharpe is undefined at zero volatility")
    return round((annual_return_pct - risk_free_pct) / annual_vol_pct, 4)


def correlation(a: Sequence[float], b: Sequence[float]) -> float:
    """Pearson correlation of two return series, in [-1, 1]."""
    if len(a) != len(b):
        raise ValueError("series must be the same length")
    _check(a, 3, "correlation")
    n = len(a)
    mean_a, mean_b = sum(a) / n, sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a == 0 or var_b == 0:
        raise ValueError("cannot correlate a flat series")
    return round(cov / math.sqrt(var_a * var_b), 4)


def correlation_matrix(series_by_symbol: dict[str, Sequence[float]]) -> tuple[list[str], list[list[float]]]:
    """Pairwise correlation of price series, truncated to their common length.

    Returns (symbols, matrix). Symbols whose series are too short or flat are
    dropped rather than shown as a misleading 0.0 - an absent row is honest, a
    fabricated zero is not.
    """
    usable: dict[str, list[float]] = {}
    shortest = min((len(s) for s in series_by_symbol.values()), default=0)
    for symbol, prices in series_by_symbol.items():
        if len(prices) < 4 or shortest < 4:
            continue
        trimmed = list(prices)[-shortest:]
        if len(set(trimmed)) <= 1:
            continue
        usable[symbol] = returns(trimmed)

    symbols = sorted(usable)
    matrix = [
        [1.0 if a == b else correlation(usable[a], usable[b]) for b in symbols]
        for a in symbols
    ]
    return symbols, matrix
