"""News: yfinance headlines, RSS, deterministic mock. All keyless.

Headlines are untrusted third-party text. Nothing here renders them as fact, and
the news agent's prompt forbids following instructions found inside them - see the
prompt-safety skill.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timezone

from src.core.cache import make_key
from src.core.contracts import DataStatus, NewsItem

_NOT_TICKERS = {
    "ETF","ETFS","IRA","IRAS","SEC","IRS","GDP","CPI","ROTH","HSA","NAV","APR","APY","USA","US",
    "CEO","CFO","AI","ESG","REIT","TIPS","RMD","YTD","EPS","PE","FOMC","FED","QQQ" ,
}
_STOP = {"what","how","why","is","are","the","a","an","of","to","in","on","for","and","about",
         "latest","news","today","tell","me","happening","with","this","week"}


def extract_symbols(text: str) -> list[str]:
    """Deliberately conservative: a false ticker sends the news agent off-topic.
    Requires $PREFIX or an all-caps token that is not a known finance acronym."""
    found: list[str] = []
    for tok in re.findall(r"\$([A-Za-z][A-Za-z.\-]{0,9})|\b([A-Z]{2,5}(?:-[A-Z]{2,4})?)\b", text or ""):
        sym = (tok[0] or tok[1]).upper()
        if tok[0] or sym not in _NOT_TICKERS:
            if sym not in found:
                found.append(sym)
    return found[:4]


def keyword_query(text: str, limit: int = 6) -> str:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", text or "") if w.lower() not in _STOP]
    return " ".join(words[:limit]) or "stock market"


class MockNews:
    name = "mock"

    def search(self, query: str, limit: int = 5) -> list[NewsItem]:
        return [
            NewsItem(title=f"Sample: markets digest {keyword_query(query, 3) or 'economic data'}",
                     source="Sample Feed", url="", summary="Illustrative headline, not real news.",
                     published=datetime.now(timezone.utc), status=DataStatus.SAMPLE),
            NewsItem(title="Sample: index funds continue to draw inflows",
                     source="Sample Feed", url="", summary="Illustrative headline, not real news.",
                     published=datetime.now(timezone.utc), status=DataStatus.SAMPLE),
        ][:limit]


class YFinanceNews:
    name = "yfinance"

    def search(self, query: str, limit: int = 5) -> list[NewsItem]:
        import yfinance as yf

        symbols = extract_symbols(query) or ["SPY"]
        items: list[NewsItem] = []
        for sym in symbols[:2]:
            try:
                raw = yf.Ticker(sym).news or []
            except Exception:  # noqa: BLE001
                continue
            for entry in raw:
                content = entry.get("content", entry)
                title = content.get("title") or entry.get("title") or ""
                if not title:
                    continue
                provider = (content.get("provider") or {}).get("displayName") if isinstance(content.get("provider"), dict) else entry.get("publisher", "")
                url = ((content.get("canonicalUrl") or {}).get("url")
                       if isinstance(content.get("canonicalUrl"), dict) else entry.get("link", "")) or ""
                items.append(NewsItem(title=title, source=provider or "Yahoo Finance", url=url,
                                      summary=(content.get("summary") or "")[:400],
                                      status=DataStatus.LIVE))
        if not items:
            raise RuntimeError("yfinance returned no headlines")
        return items[:limit]


class RssNews:
    name = "rss"

    def __init__(self, feeds: Sequence[str]) -> None:
        self._feeds = list(feeds)

    def search(self, query: str, limit: int = 5) -> list[NewsItem]:
        import feedparser

        symbols = extract_symbols(query)
        urls = list(self._feeds)
        if symbols:
            urls.insert(0, f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbols[0]}&region=US&lang=en-US")
        items: list[NewsItem] = []
        for url in urls:
            parsed = feedparser.parse(url)
            for e in getattr(parsed, "entries", [])[:limit]:
                title = getattr(e, "title", "")
                if not title:
                    continue
                items.append(NewsItem(title=title,
                                      source=getattr(getattr(e, "source", None), "title", "") or "Yahoo Finance RSS",
                                      url=getattr(e, "link", ""),
                                      summary=re.sub(r"<[^>]+>", "", getattr(e, "summary", ""))[:400],
                                      status=DataStatus.LIVE))
            if items:
                break
        if not items:
            raise RuntimeError("no RSS headlines")
        return items[:limit]


class NewsService:
    def __init__(self, providers: Sequence, cache, *, ttl: int = 1800, stale_max_age: int = 604800) -> None:
        self._providers = list(providers)
        self._cache = cache
        self._ttl = ttl
        self._stale_max = stale_max_age
        self.last_status: DataStatus = DataStatus.LIVE

    def search(self, query: str, limit: int = 5) -> list[NewsItem]:
        key = make_key("news", query.lower().strip(), str(limit))
        fresh = self._cache.get(key, self._ttl)
        if fresh:
            self.last_status = DataStatus.CACHED
            return [NewsItem(**{**r, "status": DataStatus.CACHED}) for r in fresh]

        for provider in self._providers:
            if provider.name == "mock":
                continue
            try:
                items = provider.search(query, limit)
            except Exception:  # noqa: BLE001
                continue
            if items:
                self._cache.set(key, [i.model_dump(mode="json") for i in items])
                self.last_status = DataStatus.LIVE
                return items

        stale = self._cache.get_stale(key, self._stale_max)
        if stale:
            self.last_status = DataStatus.STALE
            return [NewsItem(**{**r, "status": DataStatus.STALE}) for r in stale[0]]

        self.last_status = DataStatus.SAMPLE
        return MockNews().search(query, limit)
