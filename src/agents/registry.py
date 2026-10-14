"""Intent -> agent. Adding a seventh agent is one import and one row."""

from __future__ import annotations

from src.agents.finance_qa import FinanceQAAgent
from src.agents.goal_planning import GoalPlanningAgent
from src.agents.market import MarketAgent
from src.agents.news import NewsAgent
from src.agents.portfolio import PortfolioAgent
from src.agents.tax import TaxAgent
from src.core.contracts import Intent

AGENT_CLASSES = {
    Intent.PORTFOLIO: PortfolioAgent,
    Intent.GOAL_PLANNING: GoalPlanningAgent,
    Intent.MARKET: MarketAgent,
    Intent.NEWS: NewsAgent,
    Intent.TAX: TaxAgent,
    Intent.FINANCE_QA: FinanceQAAgent,
}

# Canonical order for assembling the final answer: the user's own situation first,
# general background last.
SECTION_ORDER = [Intent.PORTFOLIO, Intent.GOAL_PLANNING, Intent.MARKET,
                 Intent.NEWS, Intent.TAX, Intent.FINANCE_QA]


def build_agents(deps) -> dict[Intent, object]:
    return {intent: cls(deps) for intent, cls in AGENT_CLASSES.items()}
