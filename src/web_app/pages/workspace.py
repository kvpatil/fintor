"""Portfolio, Market, and Goals. Deliberately plain: one table and one chart each.

Richer dataviz (Monte Carlo fan chart, correlation heatmap) arrives in Phase 3 with
the maths that justifies it.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.core.quant import (
    class_weights, concentration_flags, diversification_score, portfolio_value, project_goal,
    risk_score, weights,
)
from src.web_app.components import data_status_chip, persona_card, persona_selector
from src.web_app.state import active_persona, get_deps


def _shell(title: str, caption: str):
    persona_selector()
    persona = active_persona()
    st.title(title)
    st.caption(caption)
    with st.sidebar:
        persona_card(persona)
    return get_deps(), persona


def portfolio() -> None:
    deps, persona = _shell("Portfolio", "Computed in Python, never by the model. "
                                        "A teaching example, not a real account.")
    if not persona.holdings:
        st.info(f"{persona.name} holds only cash (${persona.cash:,.0f}) — "
                "a deliberate starting point. Try another persona to see a funded portfolio.")
        return

    quotes = deps.market.quotes([h.symbol for h in persona.holdings])
    total, unpriced = portfolio_value(persona.holdings, quotes, persona.cash)
    w = weights(persona.holdings, quotes, persona.cash)
    div = diversification_score(persona.holdings, w)
    risk, label = risk_score(persona.holdings, w)

    st.markdown(data_status_chip(deps.market.last_status.value), unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total value", f"${total:,.0f}")
    c2.metric("Diversification", f"{div}/100")
    c3.metric("Risk score", f"{risk}/100", label)
    c4.metric("Stated tolerance", persona.risk_tolerance)

    rows = [{
        "symbol": h.symbol, "shares": h.shares, "class": h.asset_class,
        "price": quotes.get(h.symbol.upper()).price if quotes.get(h.symbol.upper()) else None,
        "weight %": w.get(h.symbol.upper(), 0.0),
    } for h in persona.holdings]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={"weight %": st.column_config.ProgressColumn(
                     "weight %", min_value=0.0, max_value=100.0, format="%.1f%%")})

    cls = class_weights(persona.holdings, w)
    fig = px.pie(names=list(cls.keys()), values=list(cls.values()), hole=0.55,
                 color_discrete_sequence=px.colors.sequential.Teal)
    fig.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
    st.plotly_chart(fig, width="stretch")

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

    chart_for = st.selectbox("Price history", symbols, index=0)
    period = st.radio("Period", ["1mo", "3mo", "6mo", "1y"], index=2, horizontal=True)
    rows, status = deps.market.history(chart_for, period)
    if rows:
        df = pd.DataFrame(rows, columns=["date", "close"])
        fig = px.line(df, x="date", y="close", color_discrete_sequence=["#1f6f5c"])
        fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10),
                          yaxis_title=None, xaxis_title=None)
        st.plotly_chart(fig, width="stretch")
        first, last = rows[0][1], rows[-1][1]
        m1, m2, m3 = st.columns(3)
        m1.metric(f"{period} change", f"{100.0 * (last - first) / first:+.2f}%")
        m2.metric("Period low", f"${min(r[1] for r in rows):,.2f}")
        m3.metric("Period high", f"${max(r[1] for r in rows):,.2f}")
        st.markdown(data_status_chip(status.value), unsafe_allow_html=True)


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
    path = pd.DataFrame(proj["yearly_path"], columns=["year", "value"])
    fig = px.area(path, x="year", y="value", color_discrete_sequence=["#1f6f5c"])
    fig.add_hline(y=target, line_dash="dash", annotation_text="target")
    fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10),
                      yaxis_title=None, xaxis_title="years")
    st.plotly_chart(fig, width="stretch")
    for note in proj["assumptions"]:
        st.caption(f"• {note}")
