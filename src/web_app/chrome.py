"""Top chrome: breadcrumb, identity readout, mode and budget chip.

One module owns the header so pages never rebuild it, and so the header's shape is
decided in one place rather than drifting page by page.
"""

from __future__ import annotations

import streamlit as st

from src.core.contracts import DataStatus
from src.web_app.state import active_persona, get_deps

# Nav dot colour by data provenance. Grey for cached is deliberate: a cached
# answer is honest, not a problem - only unreachable providers and synthetic
# data earn amber.
DOT_FOR_STATUS = {
    DataStatus.LIVE: "var(--dot-live)",
    DataStatus.CACHED: "var(--dot-cached)",
    DataStatus.STALE: "var(--dot-attention)",
    DataStatus.SAMPLE: "var(--dot-attention)",
}
NO_DOT = "transparent"


def dot_for(status: DataStatus | None, *, observed: bool = True) -> str:
    """Colour for a nav status dot. Transparent until something was observed."""
    if not observed or status is None:
        return NO_DOT
    return DOT_FOR_STATUS.get(status, NO_DOT)


def nav_state_style(deps) -> str:
    """A <style> block painting the nav dots from live system state.

    MUST be emitted AFTER the page body runs. The header renders first, and at
    that point the page has not fetched anything yet - so painting here made the
    dots lag a full interaction behind: visiting Market showed nothing, and the
    dot only appeared once you navigated away. See paint_nav_state().
    """
    observed = bool(getattr(deps.market, "observed", False))
    status = getattr(deps.market, "last_status", None)
    data_dot = dot_for(status, observed=observed)
    budget_dot = "var(--dot-attention)" if deps.meter.near_limit else NO_DOT
    return (
        "<style>:root{"
        f"--dot-market:{data_dot};"
        f"--dot-portfolio:{data_dot};"
        f"--dot-internals:{budget_dot};"
        "}</style>"
    )


def breadcrumb(group: str, title: str) -> str:
    """A location indicator, not a trail you can climb.

    The ancestors are plain text rather than links because "About Fintor" is a nav
    group, not a destination - and a breadcrumb with dead links is worse than one
    with none. Depth follows the real structure: workspace pages have no group, so
    they get two segments rather than an invented middle one.
    """
    parts = ["Fintor"]
    if group:
        parts.append(group)
    crumbs = "".join(
        f'<li><span class="bc-sep">/</span>{p}</li>' if i else f"<li>{p}</li>"
        for i, p in enumerate(parts)
    )
    return (
        '<nav class="bc" aria-label="Breadcrumb"><ol>'
        f'{crumbs}<li><span class="bc-sep">/</span>'
        f'<span class="bc-now" aria-current="page">{title}</span></li>'
        "</ol></nav>"
    )


def _mode_chip() -> str:
    deps = get_deps()
    meter = deps.meter
    if deps.offline:
        return ('<span class="chip chip-accent">offline · free</span>')
    model = getattr(deps.chain.primary, "model", "?")
    spent, budget = meter.spent_usd, meter.budget_usd
    kind = "chip-warn" if meter.near_limit else "chip"
    return (
        f'<span class="chip">{model}</span>'
        f'<span class="{kind}">${spent:.4f} / ${budget:.2f}</span>'
    )


def header(group: str, title: str) -> None:
    """Who you are and what it costs on the right; a breadcrumb only where there
    is depth to report."""
    persona = active_persona()
    # 2:3 not 3:2 - at the 1120px measure the identity side needs the room,
    # otherwise "Dev, 31 · intermediate" wraps below the chips.
    left, right = st.columns([2, 3], vertical_alignment="center")

    with left:
        # Workspace pages have no group, and "Fintor / Chat" beside a solid-green
        # Chat tab is the same fact twice. About pages have real depth, so they
        # keep the trail.
        if group:
            st.markdown(breadcrumb(group, title), unsafe_allow_html=True)

    with right:
        ident, switch = st.columns([3, 1], vertical_alignment="center")
        with ident:
            if persona is not None:
                st.markdown(
                    f'<div class="ident">{_mode_chip()}'
                    f'<span class="ident-who">{persona.name}, {persona.age}'
                    f'<span class="ident-sub"> · {persona.experience_level.value}</span>'
                    f"</span></div>",
                    unsafe_allow_html=True,
                )
        with switch:
            # "Sign out", not "Switch": clearing persona_id returns you to the
            # sign-in screen, and you have to authenticate again to get back in.
            # Identity only, though - the per-persona transcript and the
            # checkpointer thread survive, so signing back in restores the
            # conversation rather than starting over, which is the durable-state
            # feature made visible.
            if st.button("Sign out", key="chrome_switch", width="stretch",
                         help="Return to the sign-in screen"):
                st.session_state.pop("persona_id", None)
                st.session_state.pop("last_result", None)
                st.rerun()

    st.markdown('<div class="chrome-rule"></div>', unsafe_allow_html=True)


def paint_nav_state() -> None:
    """Paint the nav status dots. Call AFTER the page body has run.

    Custom properties set by a later <style> at equal specificity win, so this
    overrides the defaults in theme.py with what the page actually observed.
    """
    st.markdown(nav_state_style(get_deps()), unsafe_allow_html=True)
