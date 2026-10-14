"""Top chrome: breadcrumb, identity readout, mode and budget chip.

One module owns the header so pages never rebuild it, and so the header's shape is
decided in one place rather than drifting page by page.
"""

from __future__ import annotations

import streamlit as st

from src.web_app.state import active_persona, get_deps


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
    """Breadcrumb on the left; who you are and what it costs on the right."""
    persona = active_persona()
    left, right = st.columns([3, 2], vertical_alignment="center")

    with left:
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
            # Clears identity only. The per-persona transcript and the checkpointer
            # thread survive, so coming back restores the conversation rather than
            # starting over - which is the durable-state feature made visible.
            if st.button("Switch", key="chrome_switch", width="stretch",
                         help="Return to the sign-in screen and choose another persona"):
                st.session_state.pop("persona_id", None)
                st.session_state.pop("last_result", None)
                st.rerun()

    st.markdown('<div class="chrome-rule"></div>', unsafe_allow_html=True)
