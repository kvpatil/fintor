"""SPEC-003 acceptance criteria."""

from __future__ import annotations

import asyncio
import time

import pytest

from src.core.contracts import AgentResult, Citation, Intent
from src.workflow.verify import verify_citations


class StubAgent:
    """Minimal agent: enough to exercise the graph without a provider."""

    def __init__(self, name: str, intent: Intent, *, delay: float = 0.0,
                 citations: int = 0, boom: bool = False) -> None:
        self.name = name
        self.intent = intent
        self.section_title = name
        self._delay = delay
        self._citations = citations
        self._boom = boom

    async def run(self, query, persona=None):
        if self._boom:
            raise RuntimeError("agent exploded outside its own contract")
        if self._delay:
            await asyncio.sleep(self._delay)
        cites = [Citation(index=i, title=f"{self.name} source {i}")
                 for i in range(1, self._citations + 1)]
        body = " ".join(f"claim [{i}]" for i in range(1, self._citations + 1)) or f"{self.name} ran"
        return AgentResult(agent=self.name, intent=self.intent, text=body, citations=cites)


def _workflow(agents: dict):
    """Build a workflow with a stubbed container - no provider, no network."""
    from src.workflow.graph import FintorWorkflow

    class Stub:
        settings = type("S", (), {"workflow": {"agent_timeout_seconds": 5}})()
        agents: dict = {}

        class router:
            @staticmethod
            async def route(text):
                from src.core.contracts import RouteDecision, RouterTier

                intents = [i for i in (Intent.MARKET, Intent.TAX)
                           if i.value.split("_")[0] in text.lower()] or [Intent.FINANCE_QA]
                return RouteDecision(intents=intents, tier=RouterTier.RULES, reason="stub")

    deps = Stub()
    deps.agents = agents
    return FintorWorkflow(deps)


@pytest.mark.asyncio
async def test_graph_fanout_merges_parallel_agent_results():
    """AC1: both branches land in state - proof the operator.add reducer works.

    Without the reducer, concurrent writes to agent_results would overwrite each
    other and only the last branch home would survive.
    """
    wf = _workflow({
        Intent.MARKET: StubAgent("market", Intent.MARKET),
        Intent.TAX: StubAgent("tax", Intent.TAX),
        Intent.FINANCE_QA: StubAgent("finance_qa", Intent.FINANCE_QA),
    })
    result = await wf.ainvoke("market and tax please")
    agents_run = {r["agent"] for r in result["agent_results"]}
    assert agents_run == {"market", "tax"}
    assert len(result["final"]["sections"]) == 2


@pytest.mark.asyncio
async def test_fanout_runs_concurrently():
    """AC2: wall clock is close to the slowest agent, not the sum."""
    wf = _workflow({
        Intent.MARKET: StubAgent("market", Intent.MARKET, delay=0.4),
        Intent.TAX: StubAgent("tax", Intent.TAX, delay=0.4),
        Intent.FINANCE_QA: StubAgent("finance_qa", Intent.FINANCE_QA),
    })
    started = time.perf_counter()
    await wf.ainvoke("market and tax please")
    elapsed = time.perf_counter() - started
    assert elapsed < 0.7, f"took {elapsed:.2f}s; sequential would be >= 0.8s"


@pytest.mark.asyncio
async def test_citations_renumber_across_agents_without_collision():
    """AC3: two agents each emitting [1] must not end up sharing an index."""
    wf = _workflow({
        Intent.MARKET: StubAgent("market", Intent.MARKET, citations=2),
        Intent.TAX: StubAgent("tax", Intent.TAX, citations=2),
        Intent.FINANCE_QA: StubAgent("finance_qa", Intent.FINANCE_QA),
    })
    result = await wf.ainvoke("market and tax please")
    indices = [c["index"] for c in result["final"]["citations"]]
    assert sorted(indices) == [1, 2, 3, 4], indices
    assert len(indices) == len(set(indices)), "citation indices collided"
    assert "[3]" in result["answer"] or "[4]" in result["answer"]


@pytest.mark.asyncio
async def test_self_harm_short_circuits_before_router_and_llm():
    """AC5: the crisis path visits neither the router nor any agent."""
    wf = _workflow({Intent.FINANCE_QA: StubAgent("finance_qa", Intent.FINANCE_QA)})
    result = await wf.ainvoke("i want to kill myself")
    nodes = [t["node"] for t in result["trace"]]
    assert "router" not in nodes
    assert not any(n.startswith("agent") for n in nodes)
    assert "988" in result["answer"]
    assert "general financial education" not in result["answer"], \
        "the crisis response must not be buried in disclaimer boilerplate"


@pytest.mark.asyncio
async def test_one_raising_agent_degrades_only_its_section():
    """AC7: containment at the node, not just inside BaseAgent."""
    wf = _workflow({
        Intent.MARKET: StubAgent("market", Intent.MARKET, boom=True),
        Intent.TAX: StubAgent("tax", Intent.TAX),
        Intent.FINANCE_QA: StubAgent("finance_qa", Intent.FINANCE_QA),
    })
    result = await wf.ainvoke("market and tax please")
    assert result["answer"], "the request must still succeed"
    assert any(r["error_code"] for r in result["agent_results"])
    assert any(s["title"] == "Taxes" for s in result["final"]["sections"])


@pytest.mark.asyncio
async def test_tool_node_loops_back_and_terminates():
    """AC4: the ReAct loop calls a tool, feeds the result back, then stops.

    The iteration cap is the real subject: a model that never stops requesting
    calls must still terminate.
    """
    from langchain_core.messages import AIMessage

    from src.workflow.tools import build_tool_graph

    class FakeBound:
        """First turn requests a tool; the next turn answers."""

        def __init__(self) -> None:
            self.turns = 0

        async def ainvoke(self, messages, **kwargs):
            self.turns += 1
            if self.turns == 1:
                return AIMessage(content="", tool_calls=[
                    {"name": "get_quote", "args": {"symbols": "AAPL"}, "id": "c1"}])
            return AIMessage(content="AAPL is at $100.00 per the tool result.")

    bound = FakeBound()

    class FakeClient:
        def bind_tools(self, tools):
            return bound

    class StubMarket:
        last_status = None

        def quotes(self, symbols):
            from src.core.contracts import DataStatus, Quote

            return {s: Quote(symbol=s, price=100.0, provider="stub",
                             status=DataStatus.LIVE) for s in symbols}

        def history(self, symbol, period="6mo"):
            from src.core.contracts import DataStatus

            return [("d0", 90.0), ("d1", 100.0)], DataStatus.LIVE

    class StubDeps:
        market = StubMarket()

        class chain:
            class primary:
                _client = FakeClient()

    compiled = build_tool_graph(StubDeps(), max_iterations=3)
    assert compiled is not None

    from src.workflow.tools import run_tool_agent

    answer, trace = await run_tool_agent(compiled, "What is AAPL trading at?")
    assert "100" in answer
    assert any("get_quote" in line for line in trace), trace
    assert bound.turns == 2, "exactly one tool round trip, then a final answer"


@pytest.mark.asyncio
async def test_tool_loop_respects_the_iteration_cap():
    """A model that always requests tools must still terminate at the cap."""
    from langchain_core.messages import AIMessage

    from src.workflow.tools import build_tool_graph, run_tool_agent

    class AlwaysToolCalls:
        def __init__(self) -> None:
            self.turns = 0

        async def ainvoke(self, messages, **kwargs):
            self.turns += 1
            return AIMessage(content="", tool_calls=[
                {"name": "get_quote", "args": {"symbols": "AAPL"}, "id": f"c{self.turns}"}])

    bound = AlwaysToolCalls()

    class FakeClient:
        def bind_tools(self, tools):
            return bound

    class StubMarket:
        def quotes(self, symbols):
            from src.core.contracts import DataStatus, Quote

            return {s: Quote(symbol=s, price=100.0, provider="stub",
                             status=DataStatus.LIVE) for s in symbols}

        def history(self, symbol, period="6mo"):
            from src.core.contracts import DataStatus

            return [("d0", 100.0)], DataStatus.LIVE

    class StubDeps:
        market = StubMarket()

        class chain:
            class primary:
                _client = FakeClient()

    compiled = build_tool_graph(StubDeps(), max_iterations=2)
    await run_tool_agent(compiled, "loop forever please")
    assert bound.turns <= 3, f"loop ran {bound.turns} turns; the cap should bound it"


def test_citation_verification_strips_unresolvable_markers():
    """A model emitting [9] when three passages exist must not go unnoticed."""
    text, stripped = verify_citations("Grounded [1] and [2] but invented [9].", {1, 2})
    assert stripped == [9]
    assert "[9]" not in text
    assert "[1]" in text and "[2]" in text


def test_citation_verification_keeps_valid_markers_untouched():
    text, stripped = verify_citations("All good [1][2][3].", {1, 2, 3})
    assert stripped == []
    assert text == "All good [1][2][3]."
