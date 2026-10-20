"""Valuation must never show the user a number that is not a number.

This file exists because of a bug that reached the screen: the Portfolio page
rendered "Total value $nan", every weight blank, and the diversification and
risk scores both reading 100/100 - while the status chip said the data was
live.

The cause was a NaN close from yfinance, which is routine for partial or
holiday rows. The cost-basis fallback never fired because a quote DID exist;
it simply was not a number. And the bad quote had been cached, so it kept
happening on every load until the cache expired.
"""

from __future__ import annotations

import math

import pytest




def _nan_quote(symbol, price=float("nan"), status=None):
    from datetime import datetime, timezone

    from src.core.contracts import DataStatus, Quote

    return Quote(symbol=symbol.upper(), price=price, change_pct=None,
                 currency="USD", provider="yfinance",
                 status=status or DataStatus.CACHED,
                 as_of=datetime.now(timezone.utc))


def test_a_nan_price_falls_back_to_cost_basis_instead_of_poisoning_the_total():
    """This shipped. The portfolio page rendered "Total value $nan", every
    weight blank, and diversification and risk both reading 100/100.

    yfinance returns NaN closes for partial or holiday rows. The cost-basis
    fallback never fired because a quote DID exist - it just was not a
    number - and the bad quote was cached, so it kept happening.
    """
    from src.core.quant import portfolio_value
    from src.data.personas import get

    dev = get("dev")
    quotes = {h.symbol.upper(): _nan_quote(h.symbol) for h in dev.holdings}

    total, unpriced = portfolio_value(dev.holdings, quotes, dev.cash)

    assert math.isfinite(total), "a NaN price reached the total"
    assert total > 0
    assert sorted(unpriced) == sorted(h.symbol for h in dev.holdings), (
        "the NaN-priced holdings were not reported as unpriced")


def test_weights_agree_with_the_total_about_what_is_priceable():
    """The two must use the same test. They did not: the total fell back to
    cost basis while the weight divided NaN by it, which is why every weight
    came out blank rather than merely wrong."""
    from src.core.quant import portfolio_value, weights
    from src.data.personas import get

    dev = get("dev")
    quotes = {h.symbol.upper(): _nan_quote(h.symbol) for h in dev.holdings}

    total, _ = portfolio_value(dev.holdings, quotes, dev.cash)
    w = weights(dev.holdings, quotes, dev.cash)

    assert w, "no weights were produced at all"
    assert all(math.isfinite(v) for v in w.values())
    assert abs(sum(w.values()) - 100.0) < 1.0, f"weights do not sum to 100: {w}"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), 0.0, -5.0])
def test_no_unusable_price_is_ever_valued(bad):
    """Zero and negative are as wrong as NaN - a free share is not a price,
    and a negative one would subtract from the total."""
    from src.core.contracts import Holding
    from src.core.quant import portfolio_value

    holding = Holding(symbol="AAA", shares=10, cost_basis=100.0, asset_class="equity")
    total, unpriced = portfolio_value([holding], {"AAA": _nan_quote("AAA", bad)}, 0.0)

    assert total == 1000.0, f"price {bad} was used instead of the cost basis"
    assert unpriced == ["AAA"]


def test_the_provider_drops_non_finite_closes_at_source():
    """Fixed in _closes rather than per call site, because quotes, history,
    the moving averages, volatility and the correlation matrix all read
    through it - one NaN would otherwise surface in five places."""
    import inspect

    from src.data.market import YFinanceProvider

    source = inspect.getsource(YFinanceProvider._closes)
    assert "isfinite" in source, "non-finite closes are not filtered at source"


def test_no_persona_headline_quotes_a_percentage():
    """A headline is a fixed string; the weight shown beside it is computed
    from live prices. Quoting a percentage in one guarantees it eventually
    contradicts the other.

    It already had: Dev's headline read "70% in employer stock" while the
    Portfolio page computed 64.6% from that day's prices. Small, but it
    undercuts the product's central claim that every figure is calculated.
    """
    from src.data.personas import PERSONAS

    offenders = [f"{p.id}: {p.headline}" for p in PERSONAS if "%" in p.headline]
    assert not offenders, (
        "these headlines will drift from the computed weights: " + "; ".join(offenders))
