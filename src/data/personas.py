"""Six synthetic teaching personas.

Every one is fictional and labelled as such in the UI. They exist to demonstrate
personalization: the same corpus and the same six agents produce materially
different answers because the reader is different. Asking "should I buy more
NVDA?" as Dev and then as Walter is the clearest demo of that in the product.
"""

from __future__ import annotations

from src.core.contracts import Difficulty, Goal, Holding, Persona

PERSONAS: list[Persona] = [
    Persona(
        id="maya", name="Maya", age=24, headline="First paycheck, starting from zero",
        experience_level=Difficulty.BEGINNER, risk_tolerance="moderate", horizon_years=40,
        cash=3000.0, holdings=[],
        goals=[Goal(name="Emergency fund", target_amount=9000, current_savings=3000,
                    monthly_contribution=400, years=1.5, assumed_return_pct=0.0)],
        journey_prompts=[
            "I just started my first job. What should I do with my money first?",
            "What is an index fund, in plain English?",
            "Why does everyone say to start investing early?",
            "How much should I keep in an emergency fund?",
        ],
    ),
    Persona(
        id="dev", name="Dev", age=31, headline="70% in employer stock after an IPO",
        experience_level=Difficulty.INTERMEDIATE, risk_tolerance="aggressive", horizon_years=30,
        cash=12000.0,
        holdings=[
            Holding(symbol="NVDA", shares=260, cost_basis=72.0, asset_class="single_stock"),
            Holding(symbol="VTI", shares=40, cost_basis=235.0, asset_class="equity"),
            Holding(symbol="BND", shares=50, cost_basis=72.0, asset_class="bond"),
        ],
        goals=[Goal(name="House down payment", target_amount=150000, current_savings=12000,
                    monthly_contribution=2500, years=4, assumed_return_pct=4.0)],
        journey_prompts=[
            "Should I buy more NVDA?",
            "How concentrated is my portfolio?",
            "What happens tax-wise if I sell some of my employer stock?",
            "Why diversify if my one stock has done so well?",
        ],
    ),
    Persona(
        id="priya", name="Priya", age=38, headline="Index investor saving for a house",
        experience_level=Difficulty.INTERMEDIATE, risk_tolerance="moderate", horizon_years=22,
        cash=25000.0,
        holdings=[
            Holding(symbol="VTI", shares=210, cost_basis=198.0, asset_class="equity"),
            Holding(symbol="VXUS", shares=300, cost_basis=55.0, asset_class="international"),
            Holding(symbol="BND", shares=400, cost_basis=74.0, asset_class="bond"),
        ],
        goals=[Goal(name="House down payment", target_amount=200000, current_savings=25000,
                    monthly_contribution=3000, years=5, assumed_return_pct=5.0)],
        journey_prompts=[
            "Am I on track for a $200,000 down payment in five years?",
            "How did my mix do against the S&P 500?",
            "Should I rebalance if stocks have run up?",
            "How are capital gains taxed when I sell?",
        ],
    ),
    Persona(
        id="walter", name="Walter", age=61, headline="Four years from retirement, bond-heavy",
        experience_level=Difficulty.ADVANCED, risk_tolerance="conservative", horizon_years=4,
        cash=60000.0,
        holdings=[
            Holding(symbol="BND", shares=2600, cost_basis=78.0, asset_class="bond"),
            Holding(symbol="VTI", shares=380, cost_basis=160.0, asset_class="equity"),
            Holding(symbol="TLT", shares=300, cost_basis=104.0, asset_class="bond"),
        ],
        goals=[Goal(name="Retirement income", target_amount=1200000, current_savings=60000,
                    monthly_contribution=4000, years=4, assumed_return_pct=3.0)],
        journey_prompts=[
            "Should I buy more NVDA?",
            "What is sequence-of-returns risk and why does it matter now?",
            "How do required minimum distributions work?",
            "Is my mix too conservative four years out?",
        ],
    ),
    Persona(
        id="aisha", name="Aisha", age=29, headline="40% crypto, high risk appetite",
        experience_level=Difficulty.INTERMEDIATE, risk_tolerance="aggressive", horizon_years=30,
        cash=4000.0,
        holdings=[
            Holding(symbol="BTC-USD", shares=0.55, cost_basis=41000.0, asset_class="crypto"),
            Holding(symbol="ETH-USD", shares=6.0, cost_basis=2100.0, asset_class="crypto"),
            Holding(symbol="VOO", shares=48, cost_basis=410.0, asset_class="equity"),
        ],
        goals=[Goal(name="Financial independence", target_amount=1000000, current_savings=4000,
                    monthly_contribution=1800, years=18, assumed_return_pct=6.0)],
        journey_prompts=[
            "How risky is my portfolio really?",
            "What does correlation mean for crypto and stocks?",
            "What is volatility and how is it measured?",
            "How much of a drawdown should I expect?",
        ],
    ),
    Persona(
        id="sam", name="Sam", age=45, headline="Mid-career, optimising tax-advantaged accounts",
        experience_level=Difficulty.ADVANCED, risk_tolerance="moderate", horizon_years=20,
        cash=30000.0,
        holdings=[
            Holding(symbol="VTI", shares=300, cost_basis=180.0, asset_class="equity"),
            Holding(symbol="VXUS", shares=400, cost_basis=52.0, asset_class="international"),
            Holding(symbol="BND", shares=700, cost_basis=76.0, asset_class="bond"),
            Holding(symbol="VNQ", shares=120, cost_basis=85.0, asset_class="reit"),
        ],
        goals=[Goal(name="Retirement", target_amount=2500000, current_savings=30000,
                    monthly_contribution=5000, years=20, assumed_return_pct=5.0)],
        journey_prompts=[
            "What is an HSA and why is it called triple tax-advantaged?",
            "Which accounts should hold my bonds?",
            "How does tax-loss harvesting actually work?",
            "Traditional or Roth for my situation?",
        ],
    ),
]

BY_ID = {p.id: p for p in PERSONAS}


def get(persona_id: str | None) -> Persona | None:
    return BY_ID.get(persona_id) if persona_id else None
