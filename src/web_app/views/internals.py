"""AI Internals: the machinery, made visible.

This page is the differentiator. Everything here already happens inside the
workflow; most projects simply never show it.

Cards, but deliberately NO rail. The other pages split main/rail because their
content is a result plus the controls that produced it. This page is a stack of
wide diagnostic tables - the retrieval table alone carries eight columns, and at
the rail's main-column width they clip. Consistency in the surface language is
worth having; consistency in the grid at the cost of readable tables is not.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.web_app.components import card, cost_bar
from src.web_app.state import active_persona, get_deps, last_result
from src.web_app.theme import chip

TIER_NOTE = {
    "rules": "Tier 1 — regex signals. Free, instant.",
    "embedding": "Tier 2 — embedding k-NN against intent centroids. Free, no API call.",
    "llm": "Tier 3 — LLM classifier with structured output. The only tier that costs anything.",
    "llm_fallback_rules": "Tier 3 failed; fell back to the tier-1 result. Routing never blocks answering.",
}
CACHE_NOTE = {
    "miss": "No cache hit — the provider was called.",
    "exact": "Layer 1 — identical prompt served from disk. Zero tokens.",
    "semantic": "Layer 2 — a paraphrase matched a stored question.",
    "prompt": "Layer 3 — provider prompt cache reused the prefix.",
    "offline": "Offline mode — canned response, never billed.",
}


def _graph_section(deps) -> None:
    with card("in-graph", title="Workflow graph",
              subtitle="Generated from the compiled LangGraph via "
                       "`get_graph().draw_mermaid()`, so it cannot drift from the code."):
        from src.workflow.graph import FintorWorkflow

        mermaid = FintorWorkflow(deps).mermaid()
        try:
            import streamlit_mermaid as stmd

            # No height: the component measures its own SVG and calls
            # setFrameHeight. The 320px that used to be here clipped a 616px
            # diagram. See views/about.py::_mermaid.
            stmd.st_mermaid(mermaid, pan=False, zoom=False, show_controls=False)
        except Exception:  # noqa: BLE001 - diagram is nice-to-have, never fatal
            st.code(mermaid, language="mermaid")


def render() -> None:
    deps = get_deps()
    persona = active_persona()

    st.title("AI Internals")
    st.caption("What actually happened on the last question: routing, retrieval, caching, cost.")

    with card("in-cost", title="This session"):
        cost_bar(deps.meter)

    result = last_result()
    if not result:
        st.info("Ask something on the Chat tab, then come back — this page reports the last run.")
        _graph_section(deps)
        return

    route = result.get("route", {})
    final = result.get("final", {})

    # -- routing ---------------------------------------------------------
    tier = route.get("tier", "")
    with card("in-routing", title="Routing decision",
              subtitle="Which tier resolved the question, and why."):
        c1, c2 = st.columns([1, 2])
        c1.metric("Tier that resolved it", tier or "—")
        c1.metric("Agents selected", len(route.get("intents", [])))
        c2.markdown(f"**{TIER_NOTE.get(tier, '')}**")
        c2.write(f"Reason: {route.get('reason', '—')}")
        c2.markdown(" ".join(chip(i, "accent") for i in route.get("intents", [])),
                    unsafe_allow_html=True)
        if route.get("advice_request"):
            c2.markdown(chip("advice request detected → redirect appended", "warn"),
                        unsafe_allow_html=True)
        signals = route.get("signals")
        if signals:
            # Printed as a raw dict repr before. Defensive about the shape: this
            # is a diagnostics page and it must not be the thing that crashes.
            if isinstance(signals, dict):
                matched = "; ".join(
                    f"{intent}: {', '.join(map(str, words))}"
                    if isinstance(words, (list, tuple)) else f"{intent}: {words}"
                    for intent, words in signals.items())
            else:
                matched = ", ".join(map(str, signals))
            c2.caption(f"Matched signals — {matched}")

    # -- persona conditioning --------------------------------------------
    with card("in-persona", title="Persona conditioning",
              subtitle="The difficulty ceiling filters the corpus before ranking, so a "
                       "beginner is never served advanced passages. Each persona also "
                       "has its own checkpointer thread."):
        p1, p2, p3 = st.columns(3)
        p1.metric("Active persona", persona.name)
        p2.metric("Difficulty ceiling", persona.experience_level.value)
        p3.metric("Thread", persona.thread_id)

    # -- graph trace -----------------------------------------------------
    trace = result.get("trace", [])
    if trace:
        with card("in-trace", title="Graph trace",
                  subtitle="Each node of the workflow, in the order it ran."):
            st.dataframe(
                pd.DataFrame([{"Step": t.get("node"), "Time": t.get("ms", 0),
                               "What happened": t.get("detail", "")} for t in trace]),
                hide_index=True, width="stretch",
                column_config={"Time": st.column_config.ProgressColumn(
                    "Time", min_value=0,
                    max_value=max([t.get("ms", 0) for t in trace] + [1]), format="%d ms")},
            )

    # -- retrieval -------------------------------------------------------
    rows = []
    for ar in result.get("agent_results", []):
        for ch in ar.get("chunks", []) or []:
            rows.append({
                "Agent": ar.get("agent"), "Passage": ch.get("title"),
                "Level": ch.get("difficulty") or "—", "Cosine": ch.get("score"),
                "Dense rank": ch.get("dense_rank"), "BM25 rank": ch.get("sparse_rank"),
                "RRF": ch.get("rrf_score"), "Found by": ch.get("retrieval"),
            })
    with card("in-retrieval", title="Retrieval candidates",
              subtitle="Dense and BM25 ranks fused by Reciprocal Rank Fusion (k=60). "
                       "The cosine is recomputed afterwards, because an RRF score says "
                       "nothing absolute about relevance."):
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={"Cosine": st.column_config.ProgressColumn(
                             "Cosine", min_value=0.0, max_value=1.0, format="%.3f")})
        else:
            st.caption("No passages retrieved for this question — either it needed live "
                       "data rather than the corpus, or the relevance gate refused and "
                       "no LLM was called.")

    # -- cost + cache ----------------------------------------------------
    recs = deps.meter.records
    with card("in-calls", title="Model calls, cache tiers, and cost"):
        if recs:
            st.dataframe(
                pd.DataFrame([{
                    "Provider": r.provider, "Model": r.model, "Tier": r.tier.value,
                    "Cache": r.cache_tier.value, "Tokens in": r.input_tokens,
                    "Tokens out": r.output_tokens, "USD": round(r.usd, 6),
                    "Latency": r.latency_ms,
                    # A bare bool renders as a checkbox, which reads as something
                    # you can click. It is a record of what happened.
                    "Fallback": "Yes" if r.fallback_used else "No",
                } for r in recs[-14:]]),
                hide_index=True, width="stretch",
                column_config={
                    "USD": st.column_config.NumberColumn(format="$%.6f"),
                    "Latency": st.column_config.NumberColumn(format="%d ms"),
                })
            for t in sorted({r.cache_tier.value for r in recs}):
                st.caption(f"**{t}** — {CACHE_NOTE.get(t, '')}")
        else:
            st.caption("No model calls yet this session.")

        # A raw dict repr ("{'unassigned': 0.0}") was being printed to screen.
        spend = deps.meter.by_persona()
        if spend:
            st.caption("Spend by persona — " + " · ".join(
                f"{name}: ${amount:.5f}" for name, amount in sorted(spend.items())))

    # -- observability ---------------------------------------------------
    from src.core import tracing

    with card("in-trace-link", title="Trace"):
        if tracing.enabled():
            trace_id = st.session_state.get("last_trace_id")
            st.caption("Spans for router, each agent, and every LLM call are sent "
                       "to Langfuse, where they outlive this session — the cost "
                       "meter above only knows about the current one.")
            if trace_id:
                url = tracing.trace_url(trace_id, deps.settings)
                st.code(trace_id, language=None)
                if url:
                    st.markdown(f"[Open this run in Langfuse]({url})")
            else:
                st.caption("Ask a question to produce a trace.")
            st.caption("Known limit: prompts are scrubbed of API-key shapes and "
                       "email addresses, but Fintor has no PII redaction layer "
                       "yet, so a free-text question reaches Langfuse "
                       "substantially intact.")
        else:
            st.caption("Tracing is off — no LANGFUSE_PUBLIC_KEY / "
                       "LANGFUSE_SECRET_KEY configured. The app behaves "
                       "identically either way.")

    # -- guardrails ------------------------------------------------------
    with card("in-guardrails", title="Guardrails",
              subtitle="Every [n] the model emits must resolve to a passage actually "
                       "retrieved. A narration containing a figure absent from the "
                       "computed facts is discarded whole and replaced by a "
                       "deterministic template."):
        g1, g2, g3 = st.columns(3)
        g1.metric("Citations verified", final.get("citations_verified", 0))
        g2.metric("Markers stripped", len(final.get("citations_stripped") or []))
        narrations = [sec.get("narration") for sec in final.get("sections", [])]
        g3.metric("Template fallbacks", sum(1 for n in narrations if n == "template"))

    _graph_section(deps)
