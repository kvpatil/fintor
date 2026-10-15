"""AI Internals: the machinery, made visible.

This page is the differentiator. Everything here already happens inside the
workflow; most projects simply never show it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.web_app.components import cost_bar
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
    st.subheader("Workflow graph")
    st.caption("Generated from the compiled LangGraph via `get_graph().draw_mermaid()` — "
               "so this diagram cannot drift from the code.")
    from src.workflow.graph import FintorWorkflow

    mermaid = FintorWorkflow(deps).mermaid()
    try:
        import streamlit_mermaid as stmd

        stmd.st_mermaid(mermaid, height="320px")
    except Exception:  # noqa: BLE001 - diagram is nice-to-have, never fatal
        st.code(mermaid, language="mermaid")


def render() -> None:
    deps = get_deps()
    persona = active_persona()

    st.title("AI Internals")
    st.caption("What actually happened on the last question: routing, retrieval, caching, cost.")

    cost_bar(deps.meter)
    st.divider()

    result = last_result()
    if not result:
        st.info("Ask something on the Chat tab, then come back — this page reports the last run.")
        _graph_section(deps)
        return

    route = result.get("route", {})
    final = result.get("final", {})

    # -- routing ---------------------------------------------------------
    st.subheader("Routing decision")
    c1, c2 = st.columns([1, 2])
    tier = route.get("tier", "")
    c1.metric("Tier that resolved it", tier or "—")
    c1.metric("Agents selected", len(route.get("intents", [])))
    c2.markdown(f"**{TIER_NOTE.get(tier, '')}**")
    c2.write(f"Reason: {route.get('reason', '—')}")
    c2.markdown(" ".join(chip(i, "accent") for i in route.get("intents", [])), unsafe_allow_html=True)
    if route.get("advice_request"):
        c2.markdown(chip("advice request detected → redirect appended", "warn"), unsafe_allow_html=True)
    if route.get("signals"):
        c2.caption(f"Matched signals: {route['signals']}")

    # -- persona conditioning --------------------------------------------
    st.subheader("Persona conditioning")
    p1, p2, p3 = st.columns(3)
    p1.metric("Active persona", persona.name)
    p2.metric("Difficulty ceiling", persona.experience_level.value)
    p3.metric("Thread", persona.thread_id)
    st.caption("The ceiling filters the corpus before ranking: a beginner is never served "
               "advanced passages. Each persona also has its own checkpointer thread.")

    # -- graph trace -----------------------------------------------------
    st.subheader("Graph trace")
    trace = result.get("trace", [])
    if trace:
        st.dataframe(
            pd.DataFrame([{"node": t.get("node"), "ms": t.get("ms", 0), "detail": t.get("detail", "")}
                          for t in trace]),
            hide_index=True, width="stretch",
            column_config={"ms": st.column_config.ProgressColumn(
                "ms", min_value=0, max_value=max([t.get("ms", 0) for t in trace] + [1]), format="%d ms")},
        )

    # -- retrieval -------------------------------------------------------
    st.subheader("Retrieval candidates")
    rows = []
    for ar in result.get("agent_results", []):
        for ch in ar.get("chunks", []) or []:
            rows.append({
                "agent": ar.get("agent"), "title": ch.get("title"),
                "difficulty": ch.get("difficulty") or "—", "cosine": ch.get("score"),
                "dense #": ch.get("dense_rank"), "bm25 #": ch.get("sparse_rank"),
                "RRF": ch.get("rrf_score"), "via": ch.get("retrieval"),
            })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"cosine": st.column_config.ProgressColumn(
                         "cosine", min_value=0.0, max_value=1.0, format="%.3f")})
        st.caption("Dense and BM25 ranks are fused by Reciprocal Rank Fusion (k=60); the cosine "
                   "is recomputed afterwards because an RRF score says nothing absolute.")
    else:
        st.caption("No passages retrieved for this question — either it needed live data "
                   "rather than the corpus, or the relevance gate refused and no LLM was called.")

    # -- cost + cache ----------------------------------------------------
    st.subheader("Model calls, cache tiers, and cost")
    recs = deps.meter.records
    if recs:
        st.dataframe(
            pd.DataFrame([{
                "provider": r.provider, "model": r.model, "tier": r.tier.value,
                "cache": r.cache_tier.value, "in": r.input_tokens, "out": r.output_tokens,
                "usd": round(r.usd, 6), "ms": r.latency_ms, "fallback": r.fallback_used,
            } for r in recs[-14:]]),
            hide_index=True, width="stretch",
        )
        tiers = {r.cache_tier.value for r in recs}
        for t in sorted(tiers):
            st.caption(f"**{t}** — {CACHE_NOTE.get(t, '')}")
    st.caption(f"Per-persona spend: {deps.meter.by_persona()}")

    # -- observability ---------------------------------------------------
    st.subheader("Trace")
    from src.core import tracing

    if tracing.enabled():
        trace_id = st.session_state.get("last_trace_id")
        st.caption("Spans for router, each agent, and every LLM call are sent to "
                   "Langfuse, where they outlive this session - the cost meter "
                   "above only knows about the current one.")
        if trace_id:
            url = tracing.trace_url(trace_id, deps.settings)
            st.code(trace_id, language=None)
            if url:
                st.markdown(f"[Open this run in Langfuse]({url})")
        else:
            st.caption("Ask a question to produce a trace.")
        st.caption("Known limit: prompts are scrubbed of API-key shapes and email "
                   "addresses, but Fintor has no PII redaction layer yet, so a "
                   "free-text question reaches Langfuse substantially intact.")
    else:
        st.caption("Tracing is off - no LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY "
                   "configured. The app behaves identically either way.")

    # -- guardrails ------------------------------------------------------
    st.subheader("Guardrails")
    g1, g2, g3 = st.columns(3)
    g1.metric("Citations verified", final.get("citations_verified", 0))
    g2.metric("Markers stripped", len(final.get("citations_stripped") or []))
    narrations = [s.get("narration") for s in final.get("sections", [])]
    g3.metric("Template fallbacks", sum(1 for n in narrations if n == "template"))
    st.caption("Every [n] the model emits must resolve to a passage actually retrieved. "
               "A narration containing a figure absent from the computed facts is discarded "
               "whole and replaced by a deterministic template.")

    st.divider()
    _graph_section(deps)
