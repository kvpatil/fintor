"""Portfolio analysis. Code computes every number; the model only explains them."""

from __future__ import annotations

from src.agents.base import BaseAgent
from src.agents.narration import narrate
from src.core.contracts import AgentResult, DataStatus, Intent, Persona, Query
from src.core.quant import (
    class_weights, concentration_flags, diversification_score, portfolio_value, risk_score, weights,
)
from src.core.safety import PERSONA_NOTE, ensure_educational_disclaimer

PORTFOLIO_RULES = """Explain what the diversification and risk scores mean and what the
concentration flags imply. Do not suggest trades, allocations, or specific holdings."""

SCORE_EXPLANATIONS = {
    "diversification_score": "0-100 from three parts: breadth of effective positions (45), "
                             "spread across asset classes (35), and size of the largest position (20).",
    "risk_score": "0-100, a value-weighted blend of asset-class risk weights, plus a penalty "
                  "when any single position exceeds 40%. Descriptive, not a forecast.",
}


class PortfolioAgent(BaseAgent):
    name = "portfolio"
    intent = Intent.PORTFOLIO
    section_title = "Your portfolio"

    async def _execute(self, query: Query, persona: Persona | None) -> AgentResult:
        if persona is None or (not persona.holdings and not persona.cash):
            return AgentResult(agent=self.name, intent=self.intent, narration="template",
                               text=ensure_educational_disclaimer(
                                   "Pick a persona on the left and I'll analyse that portfolio. "
                                   "Every account here is a sample profile with simulated holdings."))

        symbols = [h.symbol for h in persona.holdings]
        quotes = self.deps.market.quotes(symbols) if symbols else {}
        status = self.deps.market.last_status

        total, unpriced = portfolio_value(persona.holdings, quotes, persona.cash)
        w = weights(persona.holdings, quotes, persona.cash)
        div = diversification_score(persona.holdings, w)
        risk, risk_label = risk_score(persona.holdings, w)
        flags = concentration_flags(persona.holdings, w)

        facts = {
            "persona": persona.name,
            "total_value_usd": total,
            "cash_usd": persona.cash,
            "weights_pct": w,
            "asset_class_weights_pct": class_weights(persona.holdings, w),
            "diversification_score": div,
            "risk_score": risk,
            "risk_label": risk_label,
            "stated_risk_tolerance": persona.risk_tolerance,
            "concentration_flags": flags,
            "unpriced_symbols": unpriced,
            "score_explanations": SCORE_EXPLANATIONS,
            "data_status": status.value,
        }

        lines = [f"{persona.name}'s portfolio is worth about ${total:,.0f}, including ${persona.cash:,.0f} in cash."]
        lines.append("Weights: " + ", ".join(f"{k} {v:.1f}%" for k, v in sorted(w.items(), key=lambda kv: -kv[1])) + ".")
        lines.append(f"Diversification score {div}/100; risk score {risk}/100 ({risk_label}), "
                     f"against a stated {persona.risk_tolerance} tolerance.")
        lines.extend(flags)
        if unpriced:
            lines.append(f"Could not price: {', '.join(unpriced)} — cost basis used instead.")
        lines.append(PERSONA_NOTE)
        template = " ".join(lines)

        text, mode = await narrate(self.deps.chain, facts, template,
                                   extra_rules=PORTFOLIO_RULES, max_words=260, question=query.text)
        notices = [n for n in [self.deps.market.last_status is not DataStatus.LIVE and
                               f"Market data status: {status.value}." or ""] if n]
        return AgentResult(agent=self.name, intent=self.intent, text=text, narration=mode,
                           data_status=status, notices=notices)
