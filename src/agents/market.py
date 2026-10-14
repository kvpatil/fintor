"""Market analysis. Entity extraction is deterministic; prices come from providers."""

from __future__ import annotations

import re

from src.agents.base import BaseAgent
from src.agents.narration import narrate
from src.core.contracts import AgentResult, DataStatus, Intent, Persona, Query
from src.core.safety import MARKET_DATA_NOTE, ensure_educational_disclaimer
from src.data.news import extract_symbols

MARKET_RULES = """Prices and returns describe the past only. Never say "today" or "now" unless
the data status is live. Never predict direction. Do not suggest buying or selling."""

_WANTS_TREND = re.compile(r"\b(trend|history|over the (last|past)|year|month|performance|doing|moved)\b", re.I)
_NAME_TO_SYMBOL = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "google": "GOOGL", "alphabet": "GOOGL",
    "amazon": "AMZN", "meta": "META", "facebook": "META", "tesla": "TSLA", "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD", "s&p 500": "SPY", "sp500": "SPY", "nasdaq": "QQQ",
    "total market": "VTI", "bonds": "BND", "treasuries": "TLT",
}


def resolve_symbols(text: str, persona: Persona | None) -> tuple[list[str], list[str]]:
    """Returns (symbols, notes). Index names map to ETF proxies, and the substitution
    is disclosed rather than silently assumed."""
    syms = extract_symbols(text)
    notes: list[str] = []
    low = (text or "").lower()
    for name, sym in _NAME_TO_SYMBOL.items():
        if name in low and sym not in syms:
            syms.append(sym)
            if sym in {"SPY", "QQQ", "VTI", "BND", "TLT"}:
                notes.append(f"{name.title()} shown via the {sym} fund as a proxy.")
    if not syms and persona and persona.holdings:
        syms = [h.symbol for h in persona.holdings][:4]
        notes.append("No ticker named, so your own holdings are shown.")
    return syms[:6], notes


class MarketAgent(BaseAgent):
    name = "market"
    intent = Intent.MARKET
    section_title = "Market"

    async def _execute(self, query: Query, persona: Persona | None) -> AgentResult:
        symbols, notes = resolve_symbols(query.text, persona)
        if not symbols:
            return AgentResult(agent=self.name, intent=self.intent, narration="template",
                               text=ensure_educational_disclaimer(
                                   "Which ticker or index would you like me to look at? "
                                   "For example AAPL, SPY, or BTC-USD."))

        quotes = self.deps.market.quotes(symbols)
        status = self.deps.market.last_status
        trend: dict[str, dict] = {}
        if _WANTS_TREND.search(query.text):
            for sym in symbols[:3]:
                rows, _st = self.deps.market.history(sym, "6mo")
                if len(rows) > 21:
                    first, last = rows[0][1], rows[-1][1]
                    trend[sym] = {
                        "period_change_pct": round(100.0 * (last - first) / first, 2),
                        "period_low": min(r[1] for r in rows),
                        "period_high": max(r[1] for r in rows),
                        "points": len(rows),
                    }

        facts = {
            "quotes": {s: {"price": q.price, "change_pct": q.change_pct, "provider": q.provider}
                       for s, q in quotes.items()},
            "six_month_trend": trend,
            "data_status": status.value,
            "proxy_notes": notes,
        }
        parts = [f"{s}: ${q.price:,.2f}" + (f" ({q.change_pct:+.2f}% on the day)" if q.change_pct is not None else "")
                 for s, q in quotes.items()]
        template = "; ".join(parts) + f". Data status: {status.value}. " + MARKET_DATA_NOTE
        if notes:
            template += " " + " ".join(notes)

        text, mode = await narrate(self.deps.chain, facts, template,
                                   extra_rules=MARKET_RULES, max_words=220, question=query.text)
        first_notice = next((q.notice for q in quotes.values() if q.notice), None)
        return AgentResult(agent=self.name, intent=self.intent, text=text, narration=mode,
                           data_status=status, notices=[first_notice] if first_notice else [])
