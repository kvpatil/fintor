"""Chat. The workflow streams node events live into st.status as it executes."""

from __future__ import annotations

import streamlit as st

from src.web_app.components import (
    card, citations_block, data_status_chip, escape_dollars, main_and_rail,
    persona_card, rail_stat,
)
from src.web_app.state import active_persona, checkpoint_path, get_deps, record_turn, run_async, turns
from src.web_app.theme import chip

# Progress labels, written for whoever is waiting. They used to read
# "Routing the question" / "Specialist agent" / "Verifying citations", which
# describe the pipeline; these describe what is being done to answer the
# question. The node names themselves are unchanged and still shown verbatim
# on the AI Internals trace.
# The label the status widget shows when a turn finishes. A CONSTANT because
# scripts/record_demo.py waits for it to know the answer has landed, and when
# this was a bare string in both places renaming it here silently broke the
# recorder: every question waited out its 120-second timeout instead, and two
# beats overran their narration by a minute.
DONE_LABEL = "Answered"

NODE_LABEL = {
    "guard": "Checking the question",
    "router": "Finding the right specialist",
    "agent": "Looking it up",
    "synthesize": "Writing the answer",
    "verify": "Checking the sources",
}


def _collect(deps, question: str, persona, status) -> dict:
    """Drive the graph and surface each node as it completes."""
    from src.workflow.graph import TRACE_EVENT, stream_query

    final: dict = {"final": {}, "route": {}, "trace": [], "agent_results": []}

    async def pump():
        async for node, payload in stream_query(
            deps, question, persona=persona, thread_id=persona.thread_id if persona else None,
            checkpoint_path=checkpoint_path(),
        ):
            if not isinstance(payload, dict):
                continue
            if node == TRACE_EVENT:
                # Terminal, and not a graph node: carries the Langfuse trace id
                # so the Internals page can link to this exact run.
                final["trace_id"] = payload.get("trace_id")
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
                # Intents only. The router TIER is an implementation detail
                # and is reported on AI Internals instead.
                detail = f" → {', '.join(final['route'].get('intents', []))}"
            if node == "agent" and payload.get("agent_results"):
                detail = f" → {payload['agent_results'][-1].get('agent','')}"
            status.write(f"✓ {label}{detail}")
        return final

    return run_async(pump())


def _assistant_rail(persona) -> None:
    """What this assistant can do for the person signed in.

    This rail used to be a "Knowledge base" card reporting a chunk count and
    explaining reciprocal rank fusion, plus a "How an answer is built" card
    describing the router's three tiers. All true, none of it about the
    customer's money. That material now lives under About Fintor > AI
    Internals, where someone who wants the engineering can go and read it.
    """
    with card("ch-can", title="What I can help with"):
        st.markdown(
            '<div class="fin-rail-note">'
            "<b>Your portfolio</b> — what you hold, how concentrated it is, and "
            "whether the parts move together.<br><br>"
            "<b>A goal</b> — what a target needs each month, and how the answer "
            "changes if returns do.<br><br>"
            "<b>Markets</b> — prices, how a holding has moved, and how that "
            "compares to a benchmark.<br><br>"
            "<b>How money works</b> — tax treatment, account types, and the terms "
            "behind a decision."
            "</div>", unsafe_allow_html=True)

    with card("ch-you", title="Your profile"):
        holdings = len(persona.holdings)
        rail_stat("Positions", f"{holdings}",
                  note=f"{persona.headline}. Horizon {persona.horizon_years} years, "
                       f"stated risk tolerance {persona.risk_tolerance}.")
        st.markdown(
            '<div class="fin-rail-note">'
            "Answers are shaped by this profile — the same question gets a "
            "different answer for someone four years from retiring than for "
            "someone with thirty years ahead of them."
            "</div>", unsafe_allow_html=True)


def render() -> None:
    persona = active_persona()

    st.title("Ask Fintor")
    persona_card(persona)

    main, rail = main_and_rail()
    with rail:
        _assistant_rail(persona)

    with main, card("ch-thread", title="Ask a finance question",
                    subtitle="Plain English. Answers are shaped by the profile "
                             "you signed in as."):
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
                st.markdown(escape_dollars(turn["r"].get("final", {}).get("text", "")))

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
            with st.status("Working on it…", expanded=True) as status:
                result = _collect(get_deps(), question, persona, status)
                status.update(label=DONE_LABEL, state="complete", expanded=False)

            final = result.get("final", {})
            st.markdown(escape_dollars(final.get("text", "_No answer produced._")))

            # The data-status chip stays: "Live data" / "Saved copy" is
            # something a customer needs in order to read the number.
            #
            # The router tier and the agent list are gone from here. They say
            # "tier: rules" and "agents: portfolio, tax" - the shape of the
            # machine, not the state of your money - and they are still
            # reported, in full, under About Fintor > AI Internals.
            bits = [data_status_chip(final.get("data_status", "live"))]
            stripped = final.get("citations_stripped") or []
            if stripped:
                # Kept, and worded for a reader rather than an engineer: a
                # dropped claim is a fact about the ANSWER, and hiding it
                # would be the dishonest option.
                bits.append(chip(
                    f"{len(stripped)} unverified claim(s) removed", "warn"))
            st.markdown(" ".join(bits), unsafe_allow_html=True)

            citations_block(final.get("citations", []))
            st.feedback("thumbs", key=f"fb::{len(turns())}")

        record_turn(question, result)
