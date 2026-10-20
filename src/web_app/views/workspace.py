"""Portfolio, Market, and Goals.

Every figure comes from `charts.py` and every number from `quant.py` or
`market_calc.py`; this module only decides what appears and in what order. The
Monte Carlo fan chart is still Phase 3 - the correlation heatmap shipped here.

Each page is a main column of results and a rail of controls and context. The
rail is read FIRST where it holds inputs: Streamlit creates the columns in
visual order, so a `with rail:` block that executes before `with main:` still
renders on the right - it just lets the main column use the values.

Each page asks `is_dark()` once and hands it to the factories, because a Plotly
figure is built in Python and cannot inherit the page's theme the way CSS does.
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
from src.web_app.components import (
    STATUS_LABEL, card, main_and_rail, persona_line, rail_rows, rail_stat, what_this_shows,
)
from src.web_app.labels import asset_class
from src.web_app.state import active_persona, get_deps
from src.web_app.theme import is_dark

PLOT = {"width": "stretch", "config": {"displayModeBar": False}}


def _shell(title: str, caption: str):
    persona = active_persona()
    st.title(title)
    st.caption(caption)
    persona_line(persona)
    return get_deps(), persona


def _status_tag(status: str) -> tuple[str, str]:
    """Card tag text and kind for a DataStatus, so the provenance rides on the
    card showing the data rather than floating loose above the page."""
    return STATUS_LABEL.get(status, (status, ""))


def portfolio() -> None:
    deps, persona = _shell("Portfolio", "Every figure here is calculated, not estimated. "
                                        "Sample account with simulated holdings.")
    if not persona.holdings:
        st.info(f"{persona.name} holds only cash (${persona.cash:,.0f}) — "
                "a deliberate starting point. Try another persona to see a funded portfolio.")
        return

    symbols = [h.symbol for h in persona.holdings]
    quotes = deps.market.quotes(symbols)
    total, unpriced = portfolio_value(persona.holdings, quotes, persona.cash)
    w = weights(persona.holdings, quotes, persona.cash)
    div = diversification_score(persona.holdings, w)
    risk, risk_label = risk_score(persona.holdings, w)
    flags = concentration_flags(persona.holdings, w)
    dark = is_dark()
    tag, tag_kind = _status_tag(deps.market.last_status.value)

    main, rail = main_and_rail()

    with main:
        with card("pf-snapshot", tag=tag, tag_kind=tag_kind, title="Portfolio snapshot",
                  subtitle="Sample account, not connected to a real brokerage.",
                  meta_label="Total value", meta_value=f"${total:,.0f}"):
            st.plotly_chart(
                charts.allocation_bar(class_weights(persona.holdings, w), dark=dark), **PLOT)

            # Column keys are what the reader sees, so they are written for a
            # reader. Formats live in column_config rather than in f-strings
            # because a NumberColumn keeps the values numeric - the column still
            # sorts as numbers.
            rows = [{
                "Symbol": h.symbol, "Shares": h.shares, "Class": asset_class(h.asset_class),
                "Price": quotes.get(h.symbol.upper()).price
                         if quotes.get(h.symbol.upper()) else None,
                "Weight": w.get(h.symbol.upper(), 0.0),
            } for h in persona.holdings]
            st.dataframe(
                pd.DataFrame(rows), hide_index=True, width="stretch",
                column_config={
                    "Shares": st.column_config.NumberColumn(format="%d"),
                    "Price": st.column_config.NumberColumn(format="$%.2f"),
                    "Weight": st.column_config.ProgressColumn(
                        "Weight", min_value=0.0, max_value=100.0, format="%.1f%%"),
                })
            if unpriced:
                st.caption(f"Could not price {', '.join(unpriced)} — cost basis used instead.")

        # --- the figure ClarityFI has no equivalent of --------------------
        histories = {}
        for symbol in symbols[:6]:
            series, _status = deps.market.history(symbol, "6mo")
            if len(series) > 20:
                histories[symbol] = [price for _date, price in series]
        names, matrix = correlation_matrix(histories)
        if len(names) >= 2:
            with card("pf-correlation", title="How these holdings move together",
                      subtitle="Pairwise correlation of daily returns over six months."):
                st.plotly_chart(charts.correlation_heatmap(names, matrix, dark=dark), **PLOT)
                what_this_shows(
                    "Diversification comes from combining holdings that do "
                    "<b>not</b> move together, so a block of strong blue is "
                    "concentration the weights alone do not show.",
                    "Red would mean a pair that moves in opposite directions.",
                    "Read the off-diagonal cells: each one is a pair of your "
                    "holdings.",
                    ignores="Past correlation is not a promise. Pairs that moved "
                            "apart for six months routinely move together in a "
                            "sell-off, which is when diversification matters most.",
                )

    with rail:
        with card("pf-diversification", title="Diversification check"):
            rail_stat("Score", f"{div}/100",
                      note="Describes the mix as it stands today. It is not a "
                           "forecast.")
        with card("pf-risk", title="Risk"):
            rail_stat("Computed", f"{risk}/100", note=f"Reads as <b>{risk_label}</b>.")
            st.markdown(
                f'<div class="fin-rail-note">Stated tolerance: '
                f'<b>{persona.risk_tolerance}</b>.</div>', unsafe_allow_html=True)
        if flags:
            with card("pf-flags", title="Worth noticing"):
                for flag in flags:
                    st.warning(flag)


def market() -> None:
    deps, persona = _shell("Market",
                           "Prices and history describe the past. They are not forecasts.")
    default = ",".join([h.symbol for h in persona.holdings][:3]) or "SPY,QQQ,BND"
    dark = is_dark()
    main, rail = main_and_rail()

    # The rail runs first because it owns the inputs the main column reads.
    with rail:
        with card("mk-controls", title="What to look at"):
            raw = st.text_input("Symbols", value=default, help="Comma-separated tickers")
            symbols = [s.strip().upper() for s in raw.split(",") if s.strip()][:6]
            chart_for = st.selectbox("Price history", symbols, index=0) if symbols else None
            period = st.radio("Period", ["1mo", "3mo", "6mo", "1y"], index=2)
            bench = st.selectbox("Compare with", ["SPY", "QQQ", "VTI", "BND"], index=0)

    if not symbols or not chart_for:
        return

    quotes = deps.market.quotes(symbols)
    rows, status = deps.market.history(chart_for, period)
    tag, tag_kind = _status_tag(status.value)

    with rail:
        with card("mk-quotes", title="Latest prices"):
            # Rows, not st.metric tiles: four tiles in a 320px rail wrap into
            # slivers, and a price list is what a terminal would show anyway.
            rail_rows([
                (sym, f"${q.price:,.2f}",
                 f"{q.change_pct:+.2f}%" if q.change_pct is not None else "—")
                for sym, q in quotes.items()
            ])

    if not rows:
        return
    dates = [d for d, _ in rows]
    closes = [p for _, p in rows]

    with main:
        with card("mk-price", tag=tag, tag_kind=tag_kind, title=f"{chart_for} price history",
                  subtitle=f"Close, with 20- and 50-day averages, over {period}.",
                  meta_label="Latest", meta_value=f"${closes[-1]:,.2f}"):
            st.plotly_chart(
                charts.price_with_averages(dates, closes, moving_average(closes, 20),
                                           moving_average(closes, 50), label=chart_for,
                                           dark=dark), **PLOT)

            # 2x2, not 4x1. Inside the card the main column is ~575px, and four
            # tiles across truncated every value to an ellipsis ("+11...",
            # "190..."). Two rows give each tile ~270px, which fits the number at
            # full size - the alternative was shrinking the type, and small
            # numbers were the complaint that started this whole pass.
            m1, m2 = st.columns(2)
            m3, m4 = st.columns(2)
            m1.metric(f"{period} change", f"{period_return(closes):+.2f}%")
            m2.metric("Largest drop", f"-{max_drawdown(closes):.1f}%",
                      help="Worst peak-to-trough decline in the window")
            # Currency lives in the LABEL: two "$" in a metric value makes
            # Streamlit render it as LaTeX, which turned this tile into green
            # maths. Whole numbers because at the metric font size
            # "189.80 - 239.24" overflows the tile and gets truncated, and cents
            # add nothing to a six-month range.
            m3.metric("Range (USD)", f"{min(closes):,.0f}–{max(closes):,.0f}")
            if len(closes) >= 10:
                m4.metric("Volatility", f"{volatility(closes):.1f}%", help="Annualised")

            what_this_shows(
                "The moving averages are context, in grey; the price itself is "
                "the subject.",
                "A price above both averages has been rising faster than its own "
                "recent history; the crossings are where that changed.",
                "Largest drop is peak-to-trough within the window, which describes "
                "the experience of holding better than volatility does.",
                ignores="Moving averages are arithmetic on past prices. They "
                        "describe what happened and carry no information about "
                        "what happens next.",
            )

        if bench != chart_for:
            brows, _ = deps.market.history(bench, period)
            n = min(len(rows), len(brows))
            if n > 5:
                with card("mk-compare", title="Indexed comparison",
                          subtitle=f"{chart_for} against {bench}, both starting at 100."):
                    st.plotly_chart(
                        charts.rebased_comparison(
                            dates[-n:],
                            {chart_for: rebase(closes[-n:]),
                             bench: rebase([p for _, p in brows[-n:]])},
                            dark=dark), **PLOT)
                    what_this_shows(
                        "Both series start at 100 on the same day, so they are "
                        "comparable on <b>one</b> axis despite different prices.",
                        "What you are comparing is the percentage move over the "
                        "window, not the share prices.",
                        ignores="Only the window shown. A different start date can "
                                "reverse which line finishes ahead.",
                    )


def goals() -> None:
    _deps, persona = _shell(
        "Goals", "Projections from an assumed rate — illustrative, not predictions.")
    goal = persona.goals[0] if persona.goals else None
    main, rail = main_and_rail()

    with rail:
        with card("gl-inputs", title="Your plan",
                  subtitle="Change anything; the projection follows."):
            target = st.number_input("Target amount",
                                     value=float(goal.target_amount if goal else 50000),
                                     step=1000.0)
            current = st.number_input("Already saved",
                                      value=float(goal.current_savings if goal else 0),
                                      step=500.0)
            monthly = st.number_input("Monthly contribution",
                                      value=float(goal.monthly_contribution if goal else 500),
                                      step=50.0)
            years = st.slider("Years", 1, 40, int(goal.years if goal else 5))
            rate = st.slider("Assumed annual return %", 0.0, 10.0,
                             float(goal.assumed_return_pct if goal else 0.0), 0.5)

    proj = project_goal(target, current, monthly, years, rate)
    central = proj["scenarios"][1]

    with main:
        with card("gl-projection", title="Projection",
                  subtitle=f"{years} years at {rate:.1f}% a year, contributing "
                           f"${monthly:,.0f} a month.",
                  meta_label="Projected value",
                  meta_value=f"${central['projected_value']:,.0f}"):
            m1, m2 = st.columns(2)
            m1.metric("On track?", "Yes" if central["on_track"] else "No",
                      None if central["on_track"] else f"-${central['shortfall']:,.0f}")
            m2.metric("Monthly needed", f"${central['monthly_needed']:,.0f}",
                      help="The contribution that would reach the target exactly")
            st.plotly_chart(
                charts.projection_area([y for y, _ in proj["yearly_path"]],
                                       [v for _, v in proj["yearly_path"]], target,
                                       dark=is_dark()), **PLOT)
            what_this_shows(
                "The line is compound growth on the money already saved plus each "
                "monthly contribution — arithmetic, not a simulation.",
                "The dashed rule is the target. Where the line crosses it is the "
                "year the goal is met at this rate.",
                ignores="One fixed rate, applied every year. Real returns arrive "
                        "unevenly, and the order they arrive in changes the outcome "
                        "even when the average is identical.",
            )

        with card("gl-scenarios", title="If returns differ",
                  subtitle="The same plan two percentage points either side of your "
                           "assumption."):
            # `on_track` as a raw bool renders as a CHECKBOX, which reads as a
            # control the user can toggle. It is an outcome, not an input.
            #
            # Five columns, not six: at the main column's width the sixth was
            # clipped mid-header ("Monthly nee..."). "Monthly needed" is the one
            # to drop - it is already a tile above, and for the two off-centre
            # scenarios the shortfall says the same thing in the units the
            # reader is already holding.
            scenarios = [{
                "Scenario": row["label"],
                "Assumed return": row["assumed_return_pct"] / 100.0,
                "Projected value": row["projected_value"],
                "On track": "Yes" if row["on_track"] else "No",
                "Shortfall": row["shortfall"],
            } for row in proj["scenarios"]]
            st.dataframe(
                pd.DataFrame(scenarios), hide_index=True, width="stretch",
                column_config={
                    "Assumed return": st.column_config.NumberColumn(format="percent"),
                    "Projected value": st.column_config.NumberColumn(format="$%,.0f"),
                    "Shortfall": st.column_config.NumberColumn(format="$%,.0f"),
                })

    with rail:
        with card("gl-assumptions", title="Assumptions"):
            for note in proj["assumptions"]:
                st.markdown(f'<div class="fin-rail-note">• {note}</div>',
                            unsafe_allow_html=True)
