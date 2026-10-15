"""The LangGraph workflow.

    START -> guard -> router --Send(fan-out)--> agent -> synthesize -> verify -> END
                        |                                   ^
                        +-----------------------------------+  (no agents needed)

`agent` is one reusable node. Fan-out is dynamic via Send(), one payload per planned
agent, and `agent_results` carries an operator.add reducer - which is what makes
concurrent writes to shared state safe. Without the reducer, parallel branches would
overwrite each other and the last one home would win.

The guard runs first, before the router and before anything costs money.
"""

from __future__ import annotations

import asyncio
import operator
import re
import time
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from src.agents.registry import SECTION_ORDER
from src.core.tracing import flush as flush_traces
from src.core.tracing import current_trace_id, pseudonym, trace_span, update_current_trace
from src.core.contracts import (
    AgentResult, DataStatus, Intent, Persona, Query,
)
from src.core.safety import (
    ADVICE_REDIRECT, SELF_HARM_RESPONSE, detect_self_harm, ensure_educational_disclaimer,
    looks_like_injection, normalize_input,
)

SECTION_TITLES = {
    Intent.PORTFOLIO: "Your portfolio", Intent.GOAL_PLANNING: "Your goal",
    Intent.MARKET: "Market", Intent.NEWS: "News", Intent.TAX: "Taxes",
    Intent.FINANCE_QA: "Background",
}


class WorkflowState(TypedDict, total=False):
    question: str
    text: str                     # normalized
    persona_id: str | None
    top_k: int
    difficulty_ceiling: Any
    history: list[dict[str, str]]
    route: dict[str, Any]
    injection_suspected: bool
    short_circuit: str | None
    # The only reducer. Parallel agent branches append; nothing overwrites.
    agent_results: Annotated[list[dict], operator.add]
    trace: Annotated[list[dict], operator.add]
    final: dict[str, Any]


def focus_question(text: str, intent: Intent) -> str:
    """Each fanned-out agent gets the question plus a reminder of its remit, so an
    agent does not comment on parts another specialist owns."""
    remit = {
        Intent.PORTFOLIO: "Answer only the part about the user's own holdings or allocation.",
        Intent.GOAL_PLANNING: "Answer only the part about saving toward a target.",
        Intent.MARKET: "Answer only the part about prices or recent performance.",
        Intent.NEWS: "Answer only the part about news or recent events.",
        Intent.TAX: "Answer only the part about tax concepts.",
        Intent.FINANCE_QA: "Answer only the general conceptual part.",
    }[intent]
    return f"{text}\n\n({remit})"


class FintorWorkflow:
    def __init__(self, deps, checkpointer=None) -> None:
        self.deps = deps
        self.agent_timeout = float(deps.settings.workflow.get("agent_timeout_seconds", 45))
        self._checkpointer = checkpointer
        self.compiled = self._build().compile(checkpointer=checkpointer)

    # -- nodes ---------------------------------------------------------------
    async def _guard(self, state: WorkflowState) -> dict:
        text = normalize_input(state.get("question", ""))
        if detect_self_harm(text):
            # Deterministic, code-generated, never persisted, and it bypasses the
            # usual disclaimer so a crisis number is not buried in boilerplate.
            return {"text": text, "short_circuit": SELF_HARM_RESPONSE,
                    "trace": [{"node": "guard", "detail": "self-harm short-circuit", "ms": 0}]}
        return {
            "text": text,
            "injection_suspected": looks_like_injection(text),
            "trace": [{"node": "guard", "detail": "normalized; no block", "ms": 0}],
        }

    async def _route(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        decision = await self.deps.router.route(state["text"])
        ms = int((time.perf_counter() - started) * 1000)
        return {
            "route": decision.model_dump(mode="json"),
            "trace": [{"node": "router", "detail": f"tier={decision.tier.value} -> "
                                                   f"{[i.value for i in decision.intents]}", "ms": ms}],
        }

    def _fan_out(self, state: WorkflowState):
        """Dynamic map. Returns a Send per planned agent - this is the fan-out."""
        if state.get("short_circuit"):
            return "synthesize"
        intents = [Intent(i) for i in state["route"]["intents"]] or [Intent.FINANCE_QA]
        return [
            Send("agent", {
                "intent": intent.value,
                "text": focus_question(state["text"], intent) if len(intents) > 1 else state["text"],
                "persona_id": state.get("persona_id"),
                "top_k": state.get("top_k", 3),
                "difficulty_ceiling": state.get("difficulty_ceiling"),
                "history": state.get("history", []),
            })
            for intent in intents
        ]

    async def _agent(self, payload: dict) -> dict:
        from src.data import personas as persona_store

        intent = Intent(payload["intent"])
        agent = self.deps.agents[intent]
        persona = persona_store.get(payload.get("persona_id"))
        query = Query(
            text=payload["text"], persona_id=payload.get("persona_id"),
            top_k=payload.get("top_k", 3), difficulty_ceiling=payload.get("difficulty_ceiling"),
            history=payload.get("history", []),
        )
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(agent.run(query, persona), timeout=self.agent_timeout)
        except TimeoutError:
            result = AgentResult(agent=agent.name, intent=intent, error_code="agent_timeout",
                                 notices=[f"The {agent.section_title.lower()} part timed out."])
        except Exception as exc:  # noqa: BLE001
            # Defence in depth. BaseAgent.run already contains errors from _execute,
            # but the node must survive an agent that fails outside that contract -
            # otherwise one broken agent takes down every fanned-out branch with it.
            result = AgentResult(agent=getattr(agent, "name", intent.value), intent=intent,
                                 error_code=type(exc).__name__,
                                 notices=[f"The {getattr(agent, 'section_title', intent.value).lower()}"
                                          f" part could not be completed."])
        ms = int((time.perf_counter() - started) * 1000)
        return {
            "agent_results": [result.model_dump(mode="json")],
            "trace": [{"node": f"agent:{agent.name}", "detail": result.error_code or
                       f"{len(result.citations)} citations, narration={result.narration}", "ms": ms}],
        }

    async def _synthesize(self, state: WorkflowState) -> dict:
        if state.get("short_circuit"):
            return {"final": {"text": state["short_circuit"], "sections": [], "citations": [],
                              "data_status": DataStatus.LIVE.value, "skip_disclaimer": True}}

        results = [AgentResult(**r) for r in state.get("agent_results", [])]
        good = [r for r in results if r.text and not r.error_code]
        failed = [r for r in results if r.error_code]
        good.sort(key=lambda r: SECTION_ORDER.index(r.intent))

        # Renumber citations across agents so two agents' [1] do not collide.
        offset = 0
        merged_citations = []
        sections = []
        multi = sum(1 for r in good if r.citations) > 1
        for result in good:
            body = result.text
            if multi and result.citations:
                shift = offset
                body = re.sub(r"\[(\d{1,2})\]", lambda m: f"[{int(m.group(1)) + shift}]", body)
                for c in result.citations:
                    c = c.model_copy(update={"index": c.index + shift})
                    merged_citations.append(c)
                offset += len(result.citations)
            else:
                merged_citations.extend(result.citations)
            sections.append({"title": SECTION_TITLES[result.intent], "agent": result.agent,
                             "text": body, "narration": result.narration,
                             "notices": result.notices})

        parts = []
        for s in sections:
            parts.append(f"**{s['title']}**\n\n{s['text']}" if len(sections) > 1 else s["text"])
        for r in failed:
            parts.append(f"_I couldn't complete the {SECTION_TITLES[r.intent].lower()} part._")

        text = "\n\n".join(parts) if parts else ensure_educational_disclaimer(
            "I wasn't able to put together an answer for that.")
        if state.get("route", {}).get("advice_request"):
            text = f"{ADVICE_REDIRECT}\n\n{text}"

        statuses = [r.data_status for r in good]
        worst = DataStatus.LIVE
        for candidate in (DataStatus.SAMPLE, DataStatus.STALE, DataStatus.CACHED):
            if candidate in statuses:
                worst = candidate
                break
        return {
            "final": {"text": text, "sections": sections,
                      "citations": [c.model_dump(mode="json") for c in merged_citations],
                      "data_status": worst.value},
            "trace": [{"node": "synthesize",
                       "detail": f"{len(sections)} section(s), {len(merged_citations)} citation(s)"
                                 + (f", {len(failed)} failed" if failed else ""), "ms": 0}],
        }

    async def _verify(self, state: WorkflowState) -> dict:
        final = dict(state.get("final", {}))
        if final.get("skip_disclaimer"):
            return {"final": final, "trace": [{"node": "verify", "detail": "skipped (crisis response)", "ms": 0}]}
        valid = {c["index"] for c in final.get("citations", [])}
        from src.workflow.verify import verify_citations

        cleaned, stripped = verify_citations(final.get("text", ""), valid)
        final["text"] = ensure_educational_disclaimer(cleaned)
        final["citations_verified"] = len(valid)
        final["citations_stripped"] = stripped
        return {"final": final,
                "trace": [{"node": "verify", "detail": f"{len(valid)} citations verified, "
                                                       f"{len(stripped)} stripped", "ms": 0}]}

    # -- assembly ------------------------------------------------------------
    def _build(self) -> StateGraph:
        graph = StateGraph(WorkflowState)
        graph.add_node("guard", self._guard)
        graph.add_node("router", self._route)
        graph.add_node("agent", self._agent)
        graph.add_node("synthesize", self._synthesize)
        graph.add_node("verify", self._verify)

        graph.add_edge(START, "guard")
        graph.add_conditional_edges(
            "guard",
            lambda s: "synthesize" if s.get("short_circuit") else "router",
            ["router", "synthesize"],
        )
        graph.add_conditional_edges("router", self._fan_out, ["agent", "synthesize"])
        graph.add_edge("agent", "synthesize")
        graph.add_edge("synthesize", "verify")
        graph.add_edge("verify", END)
        return graph

    def mermaid(self) -> str:
        """Generated from the compiled graph, so the diagram cannot drift from the code."""
        return self.compiled.get_graph().draw_mermaid()

    async def ainvoke(self, question: str, *, persona: Persona | None = None,
                      thread_id: str | None = None, top_k: int = 3) -> dict:
        state: WorkflowState = {
            "question": question,
            "persona_id": persona.id if persona else None,
            "top_k": top_k,
            "difficulty_ceiling": persona.experience_level.value if persona else None,
            "agent_results": [], "trace": [],
        }
        config = {"configurable": {"thread_id": thread_id or (persona.thread_id if persona else "default")}}
        with trace_span("workflow.chat", persona=pseudonym(persona.id, "p") if persona else None):
            out = await self.compiled.ainvoke(state, config=config if self._checkpointer else None)
            route = out.get("route", {})
            update_current_trace(
                metadata={
                    "router_tier": route.get("tier"),
                    "intents": route.get("intents"),
                    "agents": [r.get("agent") for r in out.get("agent_results", [])],
                    "citations": out.get("final", {}).get("citations_verified"),
                },
            )
        trace_id = current_trace_id()
        flush_traces()
        return {
            "trace_id": trace_id,
            "answer": out.get("final", {}).get("text", ""),
            "final": out.get("final", {}),
            "route": out.get("route", {}),
            "trace": out.get("trace", []),
            "agent_results": out.get("agent_results", []),
        }


async def run_query(deps, question: str, *, persona: Persona | None = None,
                    thread_id: str | None = None, top_k: int = 3,
                    checkpoint_path: str | None = None) -> dict:
    """Invoke the workflow with a durable thread.

    AsyncSqliteSaver rather than SqliteSaver because the graph is async and the sync
    saver raises on aget_tuple. The connection is opened per call: state lives on
    disk, so a fresh connection still sees prior checkpoints, and this avoids holding
    an event-loop-bound connection across Streamlit reruns.
    """
    if not checkpoint_path:
        wf = FintorWorkflow(deps)
        return await wf.ainvoke(question, persona=persona, thread_id=thread_id, top_k=top_k)

    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    async with aiosqlite.connect(checkpoint_path) as conn:
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        wf = FintorWorkflow(deps, checkpointer=saver)
        return await wf.ainvoke(question, persona=persona, thread_id=thread_id, top_k=top_k)


async def thread_history(checkpoint_path: str, thread_id: str) -> dict:
    """Read a persisted thread without running the graph - used to prove durability."""
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    async with aiosqlite.connect(checkpoint_path) as conn:
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        tup = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})
        return dict(tup.checkpoint.get("channel_values", {})) if tup else {}


async def stream_query(deps, question: str, *, persona: Persona | None = None,
                       thread_id: str | None = None, top_k: int = 3,
                       checkpoint_path: str | None = None):
    """Yield (node_name, payload) as each node completes.

    Real graph streaming via compiled.astream(stream_mode="updates"), which is what
    lets the UI show the agent hand-off as it happens rather than after the fact.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    state: WorkflowState = {
        "question": question,
        "persona_id": persona.id if persona else None,
        "top_k": top_k,
        "difficulty_ceiling": persona.experience_level.value if persona else None,
        "agent_results": [], "trace": [],
    }
    tid = thread_id or (persona.thread_id if persona else "default")

    if not checkpoint_path:
        wf = FintorWorkflow(deps)
        async for chunk in wf.compiled.astream(state, stream_mode="updates"):
            for node, payload in chunk.items():
                yield node, payload
        return

    async with aiosqlite.connect(checkpoint_path) as conn:
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        wf = FintorWorkflow(deps, checkpointer=saver)
        config = {"configurable": {"thread_id": tid}}
        async for chunk in wf.compiled.astream(state, config=config, stream_mode="updates"):
            for node, payload in chunk.items():
                yield node, payload
