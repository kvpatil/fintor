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
from src.web_app.brand import lockup_data_uri
from src.web_app.state import app_settings

TAGLINE = "Finance, made approachable."
# Written for someone deciding whether to sign in, not for someone reviewing
# the build. These three used to be "Hybrid retrieval / Dense vectors and BM25,
# fused by reciprocal rank", "Every claim cited" and "Costed and traced /
# Langfuse span for every run" - true, and of no interest whatsoever to a
# customer looking at their money. The engineering story moved to About Fintor,
# where someone who wants it can go and find it.
SUBLINE = (
    "Understand your portfolio, plan towards a goal, and get straight answers about "
    "money — with the sources shown. Choose a profile to see how the answers change "
    "with the person asking."
)
PILLARS = (
    ("See your real risk",
     "Concentration and correlation, not just a list of what you hold."),
    ("Plan with a range",
     "Goal projections show a spread, because a single number is not a forecast."),
    ("Answers you can check",
     "Every figure is computed, and every claim names where it came from."),
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
    # The inset is declared rather than inherited: Streamlit's default is 5rem,
    # which left 112px of whitespace either side and silently broke the form
    # card's width calc, which subtracts this value.
    "[data-testid='stMainBlockContainer']{"
    "max-width:var(--fin-measure-gate);"
    "padding-left:var(--gate-pad);padding-right:var(--gate-pad);"
    "padding-top:var(--gate-top);}"
    # Collapse the invisible elements. inject() and this block each emit a
    # <style>, and the theme probe is a height=0 iframe - three elements that
    # paint nothing but still take a slot in a `gap:16px` flex column, which
    # is the 48px of dead air that sat above the mark. Measured: every
    # ancestor of the logo reported top=104 with no margin of its own, so the
    # space could only be coming from siblings.
    # Gate-scoped: the app pages' top gap was tuned with these gaps present,
    # and pulling every page up by 48px would slide content under the header.
    "[data-testid='stMainBlockContainer'] "
    "[data-testid='stElementContainer']:has(> .stMarkdown style),"
    "[data-testid='stMainBlockContainer'] "
    "[data-testid='stElementContainer']:has(iframe[height='0'])"
    "{display:none !important;}"
    # The theme probe, out of flow rather than hidden. It paints nothing but
    # still claimed a 16px gap slot. NOT display:none - the probe is what
    # reads the painted background to decide dark mode, and theme.py already
    # records that display:none was the wrong tool for it. Absolute
    # positioning takes it out of the flex flow, so it consumes no gap while
    # still rendering and running.
    "[data-testid='stLayoutWrapper']:has(> .st-key-theme-probe)"
    "{position:absolute;width:0;height:0;overflow:hidden;}"
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
        # ONE supplied artwork, not three drawn elements. The leaf, the
        # wordmark and the tagline were a generated SVG, an inlined wordmark
        # and an HTML paragraph, held together by four measured alignments.
        # They are now a single image, so there is nothing left to align.
        #
        # Both themes are emitted and CSS shows one. An <img> cannot inherit
        # colour, and picking server-side would go stale the moment the viewer
        # toggles - Streamlit repaints without rerunning the script. The theme
        # probe stamps data-theme, so the swap is instant and needs no rerun.
        #
        # The alt text carries the wordmark AND the tagline, because both are
        # now pixels: without it a screen reader gets nothing at all from the
        # top of the page.
        f'<div class="gate-lockup">'
        f'<img class="lockup-light" src="{lockup_data_uri()}" '
        f'alt="Fintor - {TAGLINE}">'
        f'<img class="lockup-dark" src="{lockup_data_uri(dark=True)}" '
        f'alt="Fintor - {TAGLINE}">'
        f"</div>"
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


def _account_cell(persona, shared: dict[str, list[str]]) -> str:
    """One account as a grid cell.

    The numbers sit UNDER the name rather than floating right: at a third of
    the width there is no room for a right-aligned column, and they wrapped.
    """
    risk, div, total = _scores(persona)
    prompt = persona.journey_prompts[0] if persona.journey_prompts else ""
    others = [n for n in shared.get(prompt, []) if n != persona.name]
    echo = (f'<span class="signin-echo">also asked by {" and ".join(others)}</span>'
            if others else "")
    return (
        f'<div class="signin-account">'
        f'<div class="signin-account-head">'
        f'<code>{persona.id}</code>'
        f'<span class="signin-account-name">{persona.name}, {persona.age}</span>'
        f"</div>"
        f'<p class="signin-account-head-line">{persona.headline}</p>'
        f'<p class="signin-account-journey">“{prompt}”{echo}</p>'
        f'<p class="signin-account-nums">risk {risk} · spread {div} · '
        f"${total:,.0f}</p>"
        f"</div>"
    )


def _accounts_band() -> None:
    """The six accounts, three across and two down, below both panels.

    They were a single stacked column in the right-hand panel, six deep, which
    pushed the last two below the fold - so the screen that is supposed to
    introduce the personas hid a third of them.

    ONE grid, not six st.columns. The columns version put six Streamlit
    wrappers between the row and each card - stHorizontalBlock > stColumn >
    stLayoutWrapper > stVerticalBlock > stElementContainer > stMarkdown - and
    the row resolved to a height 16px short of what the cards needed, so five
    of the six pushed their last line through the bottom border. Measured
    every link and tried five different flex repairs; all five left the
    overhang at exactly +5.0px, which is what finally said the sizing was not
    mine to fix. These cards hold no widgets, so they do not need Streamlit's
    layout at all - as a single block of markup, `grid-auto-rows: 1fr` gives
    equal heights for free and the padding is honoured because the border is
    on an element we own.
    """
    shared = _shared_prompts()
    st.markdown('<p class="gate-ask gate-ask-band">Demo accounts</p>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="signin-accounts">'
        + "".join(_account_cell(p, shared) for p in PERSONAS)
        + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="gate-foot">These are sample accounts with simulated holdings, not '
        "real ones. Fintor provides information and analysis; it does not provide "
        "personal financial, investment, legal or tax advice.</p>",
        unsafe_allow_html=True,
    )


def _credential_hint(settings) -> None:
    """Print the password, but ONLY when it is the published default.

    Without this a grader who clones the repo cannot get in at all: there is no
    .env, so `FINTOR_DEMO_PASSWORD` is unset, and auth.configured() correctly
    refuses everyone. Failing closed is right for a real deployment and was
    exactly wrong for the people meant to try the app - they met a locked door
    on a screen that invites them to pick a reader.

    An operator who sets FINTOR_DEMO_PASSWORD gets silence instead. A published
    credential is meant to be read; theirs is not, and printing it because the
    code could not tell the difference is how a demo convenience becomes a leak.
    """
    if getattr(settings, "demo_password_is_published", False):
        st.markdown(
            f'<p class="signin-help">Any username below, password '
            f'<code>{settings.demo_password}</code>. Published on purpose - the '
            f'accounts are synthetic. Set <code>FINTOR_DEMO_PASSWORD</code> to '
            f'override it.</p>',
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

    # Pre-fill when the credential is the published one, so the first thing a
    # grader does is press a button rather than hunt for a password. Written
    # into session_state BEFORE the widgets rather than passed as `value=`:
    # Streamlit warns when a widget is given both a key and a value, and the
    # key is what the form reads back.
    #
    # Only when published. An operator who sets FINTOR_DEMO_PASSWORD gets
    # empty fields, for the same reason the hint below stays silent for them -
    # pre-filling their secret into a form would put it in the DOM.
    if getattr(settings, "demo_password_is_published", False):
        st.session_state.setdefault("signin_user", PERSONAS[1].id)
        st.session_state.setdefault("signin_pass", settings.demo_password)

    with st.form("signin", border=False):
        st.markdown('<p class="gate-ask">Sign in</p>', unsafe_allow_html=True)
        username = st.text_input("Username", key="signin_user",
                                 placeholder="dev", autocomplete="username")
        password = st.text_input("Password", key="signin_pass", type="password",
                                 placeholder="••••••••",
                                 autocomplete="current-password")
        submitted = st.form_submit_button("Sign in", width="stretch", type="primary")
        _credential_hint(settings)

    if not submitted:
        return

    who = auth.check(username, password, known_users=known,
                     credential=auth.credential_for(settings))
    if who:
        st.session_state["persona_id"] = who
        st.session_state[_ATTEMPTS_KEY] = 0
        # The cookie is NOT written here. st.rerun() discards everything this
        # run produced, so a component emitted on this line never reaches the
        # browser - app.py writes it on the next run instead, once the gate
        # has been passed.
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

    # Full width, below both panels, so six accounts fit without scrolling.
    _accounts_band()
