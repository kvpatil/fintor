"""The entry gate: signing in is choosing who you are.

Fintor has no accounts and no passwords by design - auth earns nothing here, and a
credential wall would slow the thing this app is for. What it does have is a first
screen that makes the persona choice deliberate and informative, which is also how
persona selection stays out of the top chrome entirely.

`app.py` calls `render()` and then `st.stop()` when no persona is set, so the tabs,
breadcrumb, and logo chrome do not exist until you are through.
"""

from __future__ import annotations

import hmac

import streamlit as st

from src.core.quant import diversification_score, portfolio_value, risk_score, weights
from src.data.personas import PERSONAS
from src.web_app.brand import logo_svg
from src.web_app.state import app_settings

TAGLINE = "Finance, taught."
SUBLINE = (
    "Six specialist agents answer money questions in plain English, grounded in a cited "
    "knowledge base. Choose a reader and the answers change with them."
)


def _scores(persona) -> tuple[int, int, float]:
    """Risk, diversification, and value from cost basis only.

    No live quotes here on purpose: the gate must render instantly and work with no
    network, so it must not trigger a market call before you are even signed in.
    """
    w = weights(persona.holdings, {}, persona.cash)
    total, _ = portfolio_value(persona.holdings, {}, persona.cash)
    risk, _label = risk_score(persona.holdings, w)
    return risk, diversification_score(persona.holdings, w), total


def _passcode_cleared() -> bool:
    """True when no passcode is configured, or the right one has been entered."""
    expected = app_settings().passcode
    if not expected:
        return True
    if st.session_state.get("gate_passcode_ok"):
        return True

    st.markdown('<p class="gate-ask">This demo is passcode protected.</p>',
                unsafe_allow_html=True)
    left, _ = st.columns([1, 1])
    with left:
        entered = st.text_input("Passcode", type="password", key="gate_passcode",
                                label_visibility="collapsed", placeholder="Passcode")
        if st.button("Continue", key="gate_passcode_submit", width="stretch"):
            # compare_digest rather than == so the check does not leak length or
            # prefix through timing. The value is never logged or echoed back.
            if hmac.compare_digest(entered or "", expected):
                st.session_state["gate_passcode_ok"] = True
                st.rerun()
            else:
                st.error("That passcode is not right. Check the value of FINTOR_PASSCODE.")
    return False


def _persona_card(persona, column) -> None:
    """One persona as a single selectable tile.

    The card and the button sit inside ONE keyed container so the CSS can draw
    a single bordered object with an accent action bar at its foot. They used
    to be two sibling blocks with Streamlit's 16px gap between them, and the
    button was a white, 400-weight, 20%-border rectangle - nothing about the
    pair said "this is one choice you can click".
    """
    risk, div, total = _scores(persona)
    with column, st.container(key=f"gate-tile-{persona.id}"):
        st.markdown(
            f'<div class="gate-card">'
            f'<p class="gate-name">{persona.name}, {persona.age}</p>'
            f'<p class="gate-head">{persona.headline}</p>'
            f'<p class="gate-meta">{persona.experience_level.value} · '
            f'{persona.risk_tolerance} · {persona.horizon_years}y horizon</p>'
            f'<p class="gate-nums">'
            f'<span>risk <b>{risk}</b></span>'
            f'<span>spread <b>{div}</b></span>'
            f'<span>${total:,.0f}</span>'
            f"</p></div>",
            unsafe_allow_html=True,
        )
        if st.button(f"Continue as {persona.name}", key=f"gate_{persona.id}",
                     width="stretch"):
            st.session_state["persona_id"] = persona.id
            st.rerun()


# The gate is a 3-up grid, not running prose, so it takes a wider measure than
# the rest of the app. Scoped to this render rather than changing --fin-measure
# globally, which the workspace and the About pages still want at 1120px.
GATE_WIDTH_CSS = (
    "<style>[data-testid='stMainBlockContainer']"
    "{max-width:var(--fin-measure-gate);}</style>"
)


def render() -> None:
    st.markdown(GATE_WIDTH_CSS, unsafe_allow_html=True)
    st.markdown('<div class="gate-wrap">', unsafe_allow_html=True)
    # `currentColor` for the wordmark, not a baked ink. The gate inlines the SVG
    # rather than loading it through <img>, so CSS reaches inside it - which
    # means the ink can follow --fin-ink and flip with the theme instantly,
    # with none of the one-rerun lag the header logo has.
    st.markdown(f'<div class="gate-logo">{logo_svg(ink="currentColor")}</div>',
                unsafe_allow_html=True)
    st.markdown(f'<p class="gate-tagline">{TAGLINE}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="gate-subline">{SUBLINE}</p>', unsafe_allow_html=True)

    if not _passcode_cleared():
        st.markdown("</div>", unsafe_allow_html=True)
        return

    st.markdown('<p class="gate-ask">Who are you today?</p>', unsafe_allow_html=True)

    # 3 x 2. The scores differ enough across these six that the grid doubles as a
    # preview of what the app will say about each of them.
    for row_start in (0, 3):
        for persona, column in zip(PERSONAS[row_start:row_start + 3], st.columns(3),
                                   strict=False):
            _persona_card(persona, column)

    st.markdown(
        '<p class="gate-foot">Every persona is a synthetic teaching example, not a real '
        "account. Fintor explains concepts; it does not give personal financial, "
        "investment, legal or tax advice.</p>",
        unsafe_allow_html=True,
    )
    if app_settings().offline:
        st.markdown('<p class="gate-foot">Running in offline mode — deterministic canned '
                    "answers, no network, no API spend.</p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
