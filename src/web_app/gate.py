"""The sign-in screen.

Fintor's accounts are the six synthetic personas: the username says who you
are, so authenticating and choosing a reader are one step rather than two. The
password is shared and set by the operator in `FINTOR_DEMO_PASSWORD`; see
`core/auth.py` for what that does and does not protect.

Two panels. The left is brand - the mark at a size it can actually be read at.
The right is the form, with the six accounts listed under it so the journeys
each persona demonstrates are visible before you pick one.

`app.py` calls `render()` and then `st.stop()` while nobody is signed in, so the
tabs, breadcrumb and logo chrome do not exist until you are through.
"""

from __future__ import annotations

import streamlit as st

from src.core import auth
from src.core.quant import diversification_score, portfolio_value, risk_score, weights
from src.data.personas import PERSONAS
from src.web_app.brand import logo_svg
from src.web_app.state import app_settings

TAGLINE = "Finance, taught."
SUBLINE = (
    "Six specialist agents answer money questions in plain English, grounded in a cited "
    "knowledge base. Sign in as one of six readers and the answers change with them."
)
PILLARS = (
    ("Hybrid retrieval", "Dense vectors and BM25, fused by reciprocal rank."),
    ("Every claim cited", "A citation that does not resolve is stripped, not shown."),
    ("Costed and traced", "Token spend per answer, and a Langfuse span for every run."),
)

# Scoped to this render only. Two jobs:
#
# 1. A wider measure - the sign-in screen is two panels, not running prose, so
#    it does not want the reading width the rest of the app uses.
# 2. Hide the stale top nav. On sign-out `st.rerun()` re-runs the script, the
#    gate calls `st.stop()` BEFORE `st.navigation()`, and because navigation is
#    never reached Streamlit sends nothing to replace it - so the tabs from the
#    previous run stay painted above the sign-in screen. Verified this is
#    cosmetic and not a bypass: clicking a stale tab highlights it and renders
#    no page, because st.stop() still runs. It looks broken all the same, and a
#    login screen wearing the app's navigation implies you are half way in.
#    The toolbar is left alone so the theme switcher still works here.
GATE_CHROME_CSS = (
    "<style>"
    "[data-testid='stMainBlockContainer']{max-width:var(--fin-measure-gate);}"
    "[data-testid='stTopNavLinkContainer'],"
    "[data-testid='stTopNavSection'],"
    "[data-testid='stLogoLink']{display:none !important;}"
    "</style>"
)

_ATTEMPTS_KEY = "signin_attempts"


def _scores(persona) -> tuple[int, int, float]:
    """Risk, diversification, and value from cost basis only.

    No live quotes here on purpose: the sign-in screen must render instantly and
    work with no network, so it must not trigger a market call before you are
    even through the door.
    """
    w = weights(persona.holdings, {}, persona.cash)
    total, _ = portfolio_value(persona.holdings, {}, persona.cash)
    risk, _label = risk_score(persona.holdings, w)
    return risk, diversification_score(persona.holdings, w), total


def _brand_panel() -> None:
    # `currentColor` for the wordmark: the gate inlines the SVG rather than
    # loading it through <img>, so CSS reaches inside and the ink follows
    # --fin-ink with no rerun lag.
    st.markdown(
        f'<div class="signin-brand">'
        f'<div class="gate-logo">{logo_svg(ink="currentColor")}</div>'
        f'<p class="gate-tagline">{TAGLINE}</p>'
        f'<p class="gate-subline">{SUBLINE}</p>'
        + "".join(
            f'<div class="signin-pillar"><b>{title}</b><span>{body}</span></div>'
            for title, body in PILLARS
        )
        + "</div>",
        unsafe_allow_html=True,
    )


def _shared_prompts() -> dict[str, list[str]]:
    """First prompts asked by more than one persona, mapped to who asks them.

    Dev and Walter both open with "Should I buy more NVDA?" and that is the
    point - personas.py calls it the clearest demonstration in the product,
    because the same question produces materially different answers for a
    31-year-old concentrated in one stock and a 61-year-old four years from
    retirement. In a flat list it just looks like a copy-paste mistake, so the
    repeat is detected and labelled rather than hidden or edited away.
    """
    seen: dict[str, list[str]] = {}
    for persona in PERSONAS:
        if persona.journey_prompts:
            seen.setdefault(persona.journey_prompts[0], []).append(persona.name)
    return {prompt: names for prompt, names in seen.items() if len(names) > 1}


def _accounts_panel() -> None:
    """The six demo accounts, so the journeys are visible before you choose."""
    shared = _shared_prompts()
    rows = []
    for persona in PERSONAS:
        risk, div, total = _scores(persona)
        prompt = persona.journey_prompts[0] if persona.journey_prompts else ""
        others = [n for n in shared.get(prompt, []) if n != persona.name]
        echo = (f'<span class="signin-echo">also asked by '
                f'{" and ".join(others)}</span>') if others else ""
        rows.append(
            f'<div class="signin-account">'
            f'<div class="signin-account-head">'
            f'<code>{persona.id}</code>'
            f'<span class="signin-account-name">{persona.name}, {persona.age}</span>'
            f'<span class="signin-account-nums">risk {risk} · spread {div} · '
            f"${total:,.0f}</span>"
            f"</div>"
            f'<p class="signin-account-head-line">{persona.headline}</p>'
            f'<p class="signin-account-journey">“{prompt}”{echo}</p>'
            f"</div>"
        )
    st.markdown(
        '<p class="gate-ask">Demo accounts</p>' + "".join(rows)
        + '<p class="gate-foot">Every persona is a synthetic teaching example, not a '
          "real account. Fintor explains concepts; it does not give personal "
          "financial, investment, legal or tax advice.</p>",
        unsafe_allow_html=True,
    )


def _sign_in_form(known: set[str]) -> None:
    settings = app_settings()

    if not auth.configured(settings):
        # Fails closed. An auth screen that waves everyone past when it is
        # misconfigured is worse than no auth screen, because it still looks
        # like a door.
        st.error("Sign-in is not configured.")
        st.markdown(
            '<p class="signin-help">Set <code>FINTOR_DEMO_PASSWORD</code> in your '
            "<code>.env</code> and restart. Until then no password is accepted — "
            "a blank one least of all.</p>",
            unsafe_allow_html=True,
        )
        return

    attempts = st.session_state.get(_ATTEMPTS_KEY, 0)
    if attempts >= auth.MAX_ATTEMPTS:
        st.error(f"Too many attempts ({attempts}). Reload the page to try again.")
        st.markdown(
            '<p class="signin-help">This counter lives in the browser session, so a '
            "reload clears it. It slows a person at the keyboard and nothing more — "
            "stated here rather than dressed up as rate limiting.</p>",
            unsafe_allow_html=True,
        )
        return

    with st.form("signin", border=False):
        st.markdown('<p class="gate-ask">Sign in</p>', unsafe_allow_html=True)
        username = st.text_input("Username", key="signin_user",
                                 placeholder="dev", autocomplete="username")
        password = st.text_input("Password", key="signin_pass", type="password",
                                 placeholder="••••••••",
                                 autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", width="stretch", type="primary")

    if not submitted:
        return

    who = auth.check(username, password, known_users=known,
                     credential=auth.credential_for(settings))
    if who:
        st.session_state["persona_id"] = who
        st.session_state[_ATTEMPTS_KEY] = 0
        st.rerun()
    else:
        st.session_state[_ATTEMPTS_KEY] = attempts + 1
        # One message for both failures. Saying which half was wrong would tell
        # an attacker which usernames exist.
        remaining = auth.MAX_ATTEMPTS - st.session_state[_ATTEMPTS_KEY]
        st.error(f"That username and password do not match. {remaining} left.")


def render() -> None:
    st.markdown(GATE_CHROME_CSS, unsafe_allow_html=True)
    known = {p.id for p in PERSONAS}

    brand, form = st.columns([5, 4], gap="large")
    with brand:
        _brand_panel()
    with form:
        with st.container(key="signin-card"):
            _sign_in_form(known)
        with st.container(key="signin-accounts"):
            _accounts_panel()
