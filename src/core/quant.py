"""Quantitative finance: pure functions, no I/O, no globals.

Code computes, the model explains. Every number Fintor shows a user originates
here or in a provider payload - never in model output. See the ai-grounding skill.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from src.core.contracts import Holding, Quote

# Rough risk weights by asset class, used for a 0-100 descriptive risk score.
# Descriptive, not predictive: it characterises a mix, it does not forecast loss.
ASSET_CLASS_RISK = {
    "cash": 2.0, "bond": 20.0, "bonds": 20.0, "reit": 62.0, "equity": 65.0,
    "international": 70.0, "small_cap": 78.0, "single_stock": 88.0, "crypto": 97.0,
}

# Broad funds hold hundreds of names; counting one as a single position would
# overstate concentration badly. The multiplier credits that look-through.
BROAD_FUNDS = {"VTI","VOO","SPY","ITOT","VXUS","VEU","IXUS","QQQ","IWM","BND","AGG","BNDX","VT","SCHB"}
_LOOK_THROUGH = 20


def portfolio_value(holdings: Sequence[Holding], quotes: dict[str, Quote], cash: float = 0.0) -> tuple[float, list[str]]:
    """Total value plus the symbols that could not be priced.

    Sample quotes are deliberately excluded: valuing a portfolio with synthetic
    prices would present fiction as fact (finance-compliance skill).
    """
    total = float(cash)
    unpriced: list[str] = []
    for h in holdings:
        q = quotes.get(h.symbol.upper())
        if q is not None and q.status.value != "sample":
            total += h.shares * q.price
        elif h.cost_basis:
            total += h.shares * h.cost_basis
            unpriced.append(h.symbol)
        else:
            unpriced.append(h.symbol)
    return round(total, 2), unpriced


def weights(holdings: Sequence[Holding], quotes: dict[str, Quote], cash: float = 0.0) -> dict[str, float]:
    total, _ = portfolio_value(holdings, quotes, cash)
    if total <= 0:
        return {}
    out: dict[str, float] = {}
    for h in holdings:
        q = quotes.get(h.symbol.upper())
        price = q.price if (q and q.status.value != "sample") else (h.cost_basis or 0.0)
        out[h.symbol.upper()] = round(100.0 * h.shares * price / total, 2)
    if cash > 0:
        out["CASH"] = round(100.0 * cash / total, 2)
    return out


def herfindahl(shares_pct: Sequence[float]) -> float:
    """HHI over percentage weights. 1/HHI is the 'effective number of positions'."""
    return sum((w / 100.0) ** 2 for w in shares_pct)


def effective_positions(holdings: Sequence[Holding], w: dict[str, float]) -> float:
    adjusted: list[float] = []
    for sym, pct in w.items():
        if sym in BROAD_FUNDS:
            adjusted.extend([pct / _LOOK_THROUGH] * _LOOK_THROUGH)
        else:
            adjusted.append(pct)
    hhi = herfindahl(adjusted)
    return round(1.0 / hhi, 1) if hhi else 0.0


def class_weights(holdings: Sequence[Holding], w: dict[str, float]) -> dict[str, float]:
    by_class: dict[str, float] = {}
    classes = {h.symbol.upper(): h.asset_class for h in holdings}
    for sym, pct in w.items():
        key = "cash" if sym == "CASH" else classes.get(sym, "equity")
        by_class[key] = round(by_class.get(key, 0.0) + pct, 2)
    return by_class


def diversification_score(holdings: Sequence[Holding], w: dict[str, float]) -> int:
    """0-100 from three components: breadth of positions, spread across asset
    classes, and the size of the largest single position."""
    if not w:
        return 0
    eff = effective_positions(holdings, w)
    breadth = min(1.0, math.log1p(eff) / math.log1p(30)) * 45
    cls = class_weights(holdings, w)
    class_hhi = herfindahl(list(cls.values()))
    spread = min(1.0, (1.0 / class_hhi) / 4.0) * 35 if class_hhi else 0.0
    top = max(w.values())
    concentration = max(0.0, 1.0 - max(0.0, top - 20.0) / 60.0) * 20
    return int(round(breadth + spread + concentration))


def risk_score(holdings: Sequence[Holding], w: dict[str, float]) -> tuple[int, str]:
    if not w:
        return 0, "Unknown"
    classes = {h.symbol.upper(): h.asset_class for h in holdings}
    score = 0.0
    for sym, pct in w.items():
        key = "cash" if sym == "CASH" else classes.get(sym, "equity")
        score += (pct / 100.0) * ASSET_CLASS_RISK.get(key, 65.0)
    if max(w.values()) > 40:
        score += 8  # concentration adds risk beyond the asset class itself
    score = min(100.0, score)
    label = ("Conservative" if score < 30 else "Moderate" if score < 55
             else "Growth" if score < 75 else "Aggressive")
    return int(round(score)), label


def concentration_flags(holdings: Sequence[Holding], w: dict[str, float]) -> list[str]:
    flags: list[str] = []
    if not w:
        return flags
    top_sym, top_pct = max(w.items(), key=lambda kv: kv[1])
    if top_sym != "CASH" and top_pct >= 25:
        flags.append(f"{top_sym} is {top_pct:.0f}% of the portfolio — a quarter or more in one position.")
    if w.get("CASH", 0) >= 30:
        flags.append(f"Cash is {w['CASH']:.0f}% of the portfolio, which may lag inflation over long horizons.")
    crypto = sum(p for s, p in w.items() if (h := next((x for x in holdings if x.symbol.upper()==s), None)) and h.asset_class == "crypto")
    if crypto >= 20:
        flags.append(f"Crypto is {crypto:.0f}% of the portfolio, an asset class with very large historical drawdowns.")
    if len([s for s in w if s != "CASH"]) == 1:
        flags.append("A single holding carries company-specific risk that diversification would reduce.")
    return flags


# --- projections --------------------------------------------------------


def future_value(current: float, monthly: float, years: float, annual_return_pct: float) -> float:
    """End-of-month contributions compounded at the monthly equivalent rate."""
    months = int(round(years * 12))
    r = (1 + annual_return_pct / 100.0) ** (1 / 12) - 1 if annual_return_pct else 0.0
    value = float(current)
    for _ in range(months):
        value = value * (1 + r) + monthly
    return round(value, 2)


def required_monthly(target: float, current: float, years: float, annual_return_pct: float) -> float:
    """Annuity solve for the contribution that reaches the target."""
    months = int(round(years * 12))
    if months <= 0:
        return 0.0
    r = (1 + annual_return_pct / 100.0) ** (1 / 12) - 1 if annual_return_pct else 0.0
    if r == 0:
        return round(max(0.0, (target - current) / months), 2)
    grown = current * (1 + r) ** months
    needed = target - grown
    if needed <= 0:
        return 0.0
    factor = ((1 + r) ** months - 1) / r
    return round(needed / factor, 2)


def yearly_path(current: float, monthly: float, years: float, annual_return_pct: float) -> list[tuple[int, float]]:
    r = (1 + annual_return_pct / 100.0) ** (1 / 12) - 1 if annual_return_pct else 0.0
    value = float(current)
    path = [(0, round(value, 2))]
    for year in range(1, int(round(years)) + 1):
        for _ in range(12):
            value = value * (1 + r) + monthly
        path.append((year, round(value, 2)))
    return path


def project_goal(target: float, current: float, monthly: float, years: float,
                 assumed_return_pct: float = 0.0, spread_pts: float = 2.0) -> dict:
    """Three deterministic scenarios around the user's own assumption.

    The default assumption is 0%: Fintor must never imply a forecast. Monte Carlo
    replaces this trio in Phase 3, which is where probability belongs.
    """
    scenarios = []
    for label, rate in (
        ("Below your assumption", max(0.0, assumed_return_pct - spread_pts)),
        ("Your assumption", assumed_return_pct),
        ("Above your assumption", assumed_return_pct + spread_pts),
    ):
        fv = future_value(current, monthly, years, rate)
        scenarios.append({
            "label": label, "assumed_return_pct": round(rate, 2), "projected_value": fv,
            "monthly_needed": required_monthly(target, current, years, rate),
            "on_track": fv >= target, "shortfall": round(max(0.0, target - fv), 2),
        })
    return {
        "target_amount": target, "current_savings": current, "monthly_contribution": monthly,
        "years": years, "scenarios": scenarios,
        "yearly_path": yearly_path(current, monthly, years, assumed_return_pct),
        "assumptions": [
            "Contributions are made at the end of each month.",
            "Returns are assumed constant; real markets are not.",
            f"The central scenario uses the {assumed_return_pct:.1f}% you supplied, not a forecast.",
        ],
    }
