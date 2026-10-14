"""Category groups.

An agent that scopes retrieval to one raw category will miss relevant material filed
elsewhere: "What is an HSA?" is a tax question whose passage lives under `retirement`.
Groups keep the scoping useful without making it wrong.
"""

from __future__ import annotations

GROUPS: dict[str, tuple[str, ...]] = {
    "tax": ("tax_education", "taxes_and_investing", "tax_efficiency", "retirement"),
    "retirement": ("retirement", "tax_education"),
    "portfolio": ("portfolio_management", "risk", "risk_adjusted_performance", "behavior"),
    "markets": ("markets", "stocks", "bonds", "etfs_and_funds"),
    "basics": ("financial_basics", "banking", "protection"),
}


def resolve(category: str | None) -> tuple[str, ...] | None:
    """A group name expands; an unknown string passes through as a raw category, so
    callers can always name a single category directly."""
    if not category:
        return None
    return GROUPS.get(category, (category,))
