"""Portfolio, Market, and Goals. Deliberately plain: one table and one chart each.

Richer dataviz (Monte Carlo fan chart, correlation heatmap) arrives in Phase 3 with
the maths that justifies it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.core.market_calc import (
    correlation_matrix, max_drawdown, moving_average, period_return, rebase, volatility,
)
from src.core.quant import (
    class_weights, concentration_flags, diversification_score, portfolio_value, project_goal,
    risk_score, weights,
)
from src.web_app import charts
from src.web_app.components import data_status_chip, persona_line
from src.web_app.state import active_persona, get_deps


def _shell(title: str, caption: str):
    persona = active_persona()
    st.title(title)
    st.caption(caption)
    persona_line(persona)
    return get_deps(), persona


def portfolio() -> None:
    deps, persona = _shell("Portfolio", "Computed in Python, never by the model. "
                                        "A teaching example, not a real account.")
    if not persona.holdings:
        st.info(f"{persona.name} holds only cash (${persona.cash:,.0f}) — "
                "a deliberate starting point. Try another persona to see a funded portfolio.")
        return

    symbols = [h.symbol for h in persona.holdings]
    quotes = deps.market.quotes(symbols)
    total, unpriced = portfolio_value(persona.holdings, quotes, persona.cash)
    w = weights(persona.holdings, quotes, persona.cash)
    div = diversification_score(persona.holdings, w)
    risk, label = risk_score(persona.holdings, w)

    st.markdown(data_status_chip(deps.market.last_status.value), unsafe_allow_html=True)

    # The total is a hero figure rather than a number in the middle of a donut:
    # it is the one number this page leads with.
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total value", f"${total:,.0f}")
    c2.metric("Diversification", f"{div}/100")
    c3.metric("Risk score", f"{risk}/100", label)
    c4.metric("Stated tolerance", persona.risk_tolerance)

    st.markdown("###### Allocation")
    st.plotly_chart(charts.allocation_bar(class_weights(persona.holdings, w)),
                    width="stretch", config={"displayModeBar": False})

    rows = [{
        "symbol": h.symbol, "shares": h.shares, "class": h.asset_class,
        "price": quotes.get(h.symbol.upper()).price if quotes.get(h.symbol.upper()) else None,
        "weight %": w.get(h.symbol.upper(), 0.0),
    } for h in persona.holdings]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"weight %": st.column_config.ProgressColumn(
                     "weight %", min_value=0.0, max_value=100.0, format="%.1f%%")})

    # --- the figure ClarityFI has no equivalent of ------------------------
    histories = {}
    for symbol in symbols[:6]:
        series, _status = deps.market.history(symbol, "6mo")
        if len(series) > 20:
            histories[symbol] = [price for _date, price in series]
    names, matrix = correlation_matrix(histories)
    if len(names) >= 2:
        st.markdown("###### How these holdings move together")
        st.caption("Pairwise correlation of daily returns over six months. Diversification "
                   "comes from combining holdings that do **not** move together, so a block "
                   "of dark blue is concentration that the weights alone do not show.")
        st.plotly_chart(charts.correlation_heatmap(names, matrix),
                        width="stretch", config={"displayModeBar": False})

    for flag in concentration_flags(persona.holdings, w):
        st.warning(flag)
    if unpriced:
        st.caption(f"Could not price {', '.join(unpriced)} — cost basis used instead.")


def market() -> None:
    deps, persona = _shell("Market", "Prices and history describe the past. They are not forecasts.")
    default = ",".join([h.symbol for h in persona.holdings][:3]) or "SPY,QQQ,BND"
    raw = st.text_input("Symbols", value=default, help="Comma-separated tickers")
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()][:6]
    if not symbols:
        return

    quotes = deps.market.quotes(symbols)
    st.markdown(data_status_chip(deps.market.last_status.value), unsafe_allow_html=True)
    cols = st.columns(min(len(quotes), 4) or 1)
    for i, (sym, q) in enumerate(quotes.items()):
        cols[i % len(cols)].metric(sym, f"${q.price:,.2f}",
                                   f"{q.change_pct:+.2f}%" if q.change_pct is not None else None)

    left, right = st.columns([2, 1])
    chart_for = left.selectbox("Price history", symbols, index=0)
    period = right.radio("Period", ["1mo", "3mo", "6mo", "1y"], index=2, horizontal=True)
    rows, status = deps.market.history(chart_for, period)
    if not rows:
        return

    dates = [d for d, _ in rows]
    closes = [p for _, p in rows]

    st.plotly_chart(
        charts.price_with_averages(dates, closes, moving_average(closes, 20),
                                   moving_average(closes, 50), label=chart_for),
        width="stretch", config={"displayModeBar": False})

    # Stat tiles: a handful of headline numbers is a KPI row, not a chart.
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{period} change", f"{period_return(closes):+.2f}%")
    m2.metric("Largest drop", f"-{max_drawdown(closes):.1f}%",
              help="Worst peak-to-trough decline in the window")
    # Currency lives in the LABEL: two "$" in a metric value makes Streamlit
    # render it as LaTeX, which turned this tile into green maths.
    # Whole numbers: at the metric font size, "189.80 - 239.24" overflows the
    # tile and Streamlit truncates it to "189.80 - ...". Cents add nothing to a
    # six-month range.
    m3.metric("Range (USD)", f"{min(closes):,.0f}–{max(closes):,.0f}")
    if len(closes) >= 10:
        m4.metric("Volatility", f"{volatility(closes):.1f}%", help="Annualised")
    st.markdown(data_status_chip(status.value), unsafe_allow_html=True)

    # --- rebased comparison: one axis, never two ---------------------------
    bench = st.selectbox("Compare with", ["SPY", "QQQ", "VTI", "BND"], index=0)
    if bench != chart_for:
        brows, _ = deps.market.history(bench, period)
        n = min(len(rows), len(brows))
        if n > 5:
            st.markdown("###### Indexed comparison")
            st.caption(f"Both series start at 100 on the same day, so {chart_for} and {bench} "
                       "are comparable on one axis despite different prices.")
            st.plotly_chart(
                charts.rebased_comparison(
                    dates[-n:],
                    {chart_for: rebase(closes[-n:]), bench: rebase([p for _, p in brows[-n:]])}),
                width="stretch", config={"displayModeBar": False})


def goals() -> None:
    deps, persona = _shell("Goals", "Projections from an assumed rate — illustrative, not predictions.")
    goal = persona.goals[0] if persona.goals else None
    c1, c2, c3 = st.columns(3)
    target = c1.number_input("Target amount", value=float(goal.target_amount if goal else 50000), step=1000.0)
    current = c2.number_input("Already saved", value=float(goal.current_savings if goal else 0), step=500.0)
    monthly = c3.number_input("Monthly contribution", value=float(goal.monthly_contribution if goal else 500), step=50.0)
    c4, c5 = st.columns(2)
    years = c4.slider("Years", 1, 40, int(goal.years if goal else 5))
    rate = c5.slider("Assumed annual return %", 0.0, 10.0, float(goal.assumed_return_pct if goal else 0.0), 0.5)

    proj = project_goal(target, current, monthly, years, rate)
    central = proj["scenarios"][1]
    m1, m2, m3 = st.columns(3)
    m1.metric("Projected value", f"${central['projected_value']:,.0f}")
    m2.metric("On track?", "Yes" if central["on_track"] else "No",
              None if central["on_track"] else f"-${central['shortfall']:,.0f}")
    m3.metric("Monthly needed", f"${central['monthly_needed']:,.0f}")

    st.dataframe(pd.DataFrame(proj["scenarios"]), hide_index=True, width="stretch")
    st.plotly_chart(
        charts.projection_area([y for y, _ in proj["yearly_path"]],
                               [v for _, v in proj["yearly_path"]], target),
        width="stretch", config={"displayModeBar": False})
    for note in proj["assumptions"]:
        st.caption(f"• {note}")
