"""Chat. The workflow streams node events live into st.status as it executes."""

from __future__ import annotations

import streamlit as st

from src.web_app.components import citations_block, data_status_chip, persona_card, persona_selector
from src.web_app.state import active_persona, checkpoint_path, get_deps, record_turn, run_async, turns
from src.web_app.theme import chip

NODE_LABEL = {
    "guard": "Safety and PII guard",
    "router": "Routing the question",
    "agent": "Specialist agent",
    "synthesize": "Assembling the answer",
    "verify": "Verifying citations",
}


def _collect(deps, question: str, persona, status) -> dict:
    """Drive the graph and surface each node as it completes."""
    from src.workflow.graph import stream_query

    final: dict = {"final": {}, "route": {}, "trace": [], "agent_results": []}

    async def pump():
        async for node, payload in stream_query(
            deps, question, persona=persona, thread_id=persona.thread_id if persona else None,
            checkpoint_path=checkpoint_path(),
        ):
            if not isinstance(payload, dict):
                continue
            for key in ("final", "route"):
                if payload.get(key):
                    final[key] = payload[key]
            for key in ("trace", "agent_results"):
                if payload.get(key):
                    final[key] = final.get(key, []) + list(payload[key])
            label = NODE_LABEL.get(node, node)
            detail = ""
            if node == "router" and final["route"]:
                detail = f" → {', '.join(final['route'].get('intents', []))} (tier: {final['route'].get('tier','')})"
            if node == "agent" and payload.get("agent_results"):
                detail = f" → {payload['agent_results'][-1].get('agent','')}"
            status.write(f"✓ {label}{detail}")
        return final

    return run_async(pump())


def render() -> None:
    deps = get_deps()
    persona_selector()
    persona = active_persona()

    st.title("Ask Fintor")
    st.caption("Six specialist agents, grounded in a cited knowledge base. "
               "Education only — never buy or sell advice.")

    with st.sidebar:
        persona_card(persona)
        st.markdown("**Try one of these**")
        for i, prompt in enumerate(persona.journey_prompts):
            if st.button(prompt, key=f"jp{i}", width="stretch"):
                st.session_state["pending_q"] = prompt
        mode = "Offline (free)" if deps.offline else f"Live · {getattr(deps.chain.primary,'model','?')}"
        st.markdown(chip(mode, "accent" if deps.offline else ""), unsafe_allow_html=True)

    for turn in turns():
        with st.chat_message("user"):
            st.write(turn["q"])
        with st.chat_message("assistant"):
            st.markdown(turn["r"].get("final", {}).get("text", ""))

    typed = st.chat_input("Ask about investing, taxes, your portfolio, or a goal…")
    question = typed or st.session_state.pop("pending_q", None)

    if not question:
        if not turns():
            st.info("Pick a persona on the left, then ask a question or tap a suggested prompt.")
        return

    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.status("Running the workflow…", expanded=True) as status:
            result = _collect(deps, question, persona, status)
            status.update(label="Done", state="complete", expanded=False)

        final = result.get("final", {})
        st.markdown(final.get("text", "_No answer produced._"))

        bits = [data_status_chip(final.get("data_status", "live"))]
        route = result.get("route", {})
        if route:
            bits.append(chip(f"router: {route.get('tier','')}"))
            bits.append(chip(f"agents: {', '.join(route.get('intents', []))}"))
        stripped = final.get("citations_stripped") or []
        if stripped:
            bits.append(chip(f"{len(stripped)} bad citation(s) stripped", "warn"))
        st.markdown(" ".join(bits), unsafe_allow_html=True)

        citations_block(final.get("citations", []))
        st.feedback("thumbs", key=f"fb::{len(turns())}")

    record_turn(question, result)
