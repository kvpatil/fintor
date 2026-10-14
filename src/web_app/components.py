"""Shared render helpers. Pages render; they never contain business logic."""

from __future__ import annotations

import streamlit as st

from src.web_app.theme import chip

STATUS_LABEL = {"live": ("Live data", "accent"), "cached": ("Saved copy", ""),
                "stale": ("Last known", "warn"), "sample": ("SAMPLE DATA", "warn")}


def persona_card(persona) -> None:
    st.markdown(
        f'<div class="fin-persona"><b>{persona.name}, {persona.age}</b><br>'
        f'<span>{persona.headline}</span><br>'
        f'<span>{persona.experience_level.value} · {persona.risk_tolerance} risk · '
        f'{persona.horizon_years}-year horizon</span></div>',
        unsafe_allow_html=True,
    )


def persona_selector() -> None:
    from src.data.personas import PERSONAS

    st.sidebar.markdown("**Who are you today?**")
    ids = [p.id for p in PERSONAS]
    labels = {p.id: f"{p.name}, {p.age} — {p.headline}" for p in PERSONAS}
    current = st.session_state.get("persona_id", "maya")
    chosen = st.sidebar.radio(
        "Persona", ids, index=ids.index(current) if current in ids else 0,
        format_func=lambda i: labels[i], label_visibility="collapsed", key="persona_radio",
    )
    if chosen != current:
        st.session_state["persona_id"] = chosen
        st.session_state.pop("last_result", None)
    st.session_state.setdefault("persona_id", chosen)
    st.sidebar.caption("Every persona is a teaching example, not a real account.")


def data_status_chip(status: str) -> str:
    label, kind = STATUS_LABEL.get(status, (status, ""))
    return chip(label, kind)


def citations_block(citations: list[dict]) -> None:
    if not citations:
        return
    seen = set()
    with st.expander(f"Sources ({len(citations)})", expanded=False):
        for c in citations:
            key = (c.get("title"), c.get("source_url"))
            if key in seen:
                continue
            seen.add(key)
            url, title = c.get("source_url", ""), c.get("title", "")
            name = c.get("source_name", "")
            line = f"**[{c['index']}] {title}** — {name}"
            if url:
                line += f" · [source]({url})"
            st.markdown(line)
            if c.get("excerpt"):
                st.caption(c["excerpt"])


def cost_bar(meter) -> None:
    s = meter.summary()
    spent, budget = s["spent_usd"], s["budget_usd"]
    frac = min(1.0, spent / budget) if budget else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Session spend", f"${spent:.5f}")
    c2.metric("Budget left", f"${s['remaining_usd']:.5f}")
    c3.metric("Model calls", s["calls"])
    c4.metric("Cache hits", f"{s['cache_hits']} ({s['hit_rate']:.0%})")
    st.progress(frac, text=f"${spent:.5f} of ${budget:.2f} session budget")
    if meter.near_limit:
        st.warning("Approaching the session budget. Set FINTOR_OFFLINE=1 to keep working for free.")
