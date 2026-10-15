"""Chat. The workflow streams node events live into st.status as it executes."""

from __future__ import annotations

import streamlit as st

from src.web_app.components import (
    answer_markdown, card, citations_block, data_status_chip, main_and_rail,
    persona_card, rail_stat,
)
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


def _knowledge_rail(deps) -> None:
    """What the answers are grounded in. The retrieval design is the part of
    Fintor most worth seeing, so it belongs on screen rather than in a doc."""
    with card("ch-kb", title="Knowledge base"):
        try:
            count = deps.retriever.count()
        except Exception:  # noqa: BLE001 - the rail must never break the page
            count = None
        if count is not None:
            rail_stat("Chunks", f"{count:,}",
                      note="Retrieved by <b>hybrid search</b>: dense vectors and "
                           "BM25 run separately, then fuse by reciprocal rank. "
                           "Keyword-only misses paraphrases; vectors alone miss "
                           "exact terms like a form number.")
        else:
            st.markdown('<div class="fin-rail-note">Index not loaded.</div>',
                        unsafe_allow_html=True)

    with card("ch-how", title="How an answer is built"):
        st.markdown(
            '<div class="fin-rail-note">'
            'A three-tier router picks the specialists: regex first, then '
            'nearest-neighbour against intent centroids, and only then a model '
            'call. Most questions never reach tier three.<br><br>'
            'Every claim is cited against a retrieved chunk. A citation that '
            'does not resolve is <b>stripped</b> rather than shown, and the '
            'count of stripped citations is reported with the answer.'
            '</div>', unsafe_allow_html=True)


def render() -> None:
    persona = active_persona()

    st.title("Ask Fintor")
    persona_card(persona)

    main, rail = main_and_rail()
    with rail:
        _knowledge_rail(get_deps())

    with main, card("ch-thread", title="Ask a finance question",
                    subtitle="Plain English. The answer changes with the reader "
                             "you chose."):
        # The journey prompts moved out of the sidebar into the body, but they
        # still set session_state["pending_q"] - so the pickup below is
        # unchanged. Shown only on an empty transcript: once you are in a
        # conversation they are clutter rather than an invitation.
        if not turns():
            st.markdown('<p class="prompt-hint">Try one of these</p>',
                        unsafe_allow_html=True)
            for row_start in (0, 2):
                prompts = persona.journey_prompts[row_start:row_start + 2]
                for prompt, column in zip(prompts, st.columns(2), strict=False):
                    with column:
                        if st.button(prompt, key=f"jp{row_start}-{prompt[:16]}",
                                     width="stretch"):
                            st.session_state["pending_q"] = prompt

        for turn in turns():
            with st.chat_message("user"):
                st.write(turn["q"])
            with st.chat_message("assistant"):
                st.markdown(answer_markdown(turn["r"].get("final", {}).get("text", "")))

        # Inside a container chat_input renders inline rather than pinned to the
        # viewport bottom, which is what we want: it reads as the foot of the
        # conversation card rather than as a floating app-wide bar.
        typed = st.chat_input("Ask about investing, taxes, your portfolio, or a goal…")
        question = typed or st.session_state.pop("pending_q", None)

        if not question:
            return

        with st.chat_message("user"):
            st.write(question)

        with st.chat_message("assistant"):
            with st.status("Running the workflow…", expanded=True) as status:
                result = _collect(get_deps(), question, persona, status)
                status.update(label="Done", state="complete", expanded=False)

            final = result.get("final", {})
            st.markdown(answer_markdown(final.get("text", "_No answer produced._")))

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
