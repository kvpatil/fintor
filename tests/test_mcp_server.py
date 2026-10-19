"""The MCP server, tested through the protocol's own dispatch.

`server.call_tool(name, args)` is what a client invokes, so that is what runs
here - not the undecorated Python functions. Calling those directly would
leave the registration, the generated input schema and the JSON round-trip
untested, which is precisely the layer an MCP server IS.

Two properties matter more than the arithmetic, because the arithmetic is
already covered by test_quant.py and test_market_calc.py:

  * every tool DELEGATES - a result must equal what the underlying quant /
    market_calc function returns, or logic has quietly grown a second home
    behind the protocol boundary where nothing can reach it;
  * no tool calls a model or the network. The socket block in conftest makes
    the second half of that automatic.
"""

from __future__ import annotations

import json

import pytest

from src.mcp_server.server import server

DEV_HOLDINGS = [
    {"symbol": "NVDA", "shares": 100, "cost_basis": 300.0, "asset_class": "equity"},
    {"symbol": "VTI", "shares": 20, "cost_basis": 250.0, "asset_class": "equity"},
    {"symbol": "BND", "shares": 30, "cost_basis": 70.0, "asset_class": "bond"},
]


async def call(name: str, **arguments):
    """Dispatch through MCP and return the structured payload.

    The SDK hands back a CallToolResult carrying BOTH a JSON text block and a
    parsed `structured_content`. Preferring the structured form and falling
    back to parsing the text keeps this working across SDK versions - 2.x
    also renamed `inputSchema` to `input_schema`, so the surface does move.
    """
    result = await server.call_tool(name, arguments)

    assert getattr(result, "is_error", False) is False, (
        f"{name} reported an error: {result!r}")

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        # A bare list is wrapped under "result" by the SDK's schema.
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured

    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"{name} returned nothing readable: {result!r}")


# --- registration --------------------------------------------------------


async def test_the_server_advertises_its_tools_with_descriptions():
    """A tool with no description is unusable from a client: the model picks
    tools by reading them."""
    tools = await server.list_tools()
    by_name = {t.name: t for t in tools}

    assert {"analyze_portfolio", "project_goal", "analyze_price_series",
            "correlate", "list_demo_personas", "search_knowledge_base"} <= set(by_name)

    for tool in tools:
        assert tool.description and len(tool.description) > 30, (
            f"{tool.name} has no usable description")
        assert tool.input_schema, f"{tool.name} advertises no input schema"


async def test_the_portfolio_tool_declares_the_arguments_it_needs():
    """The schema is generated from the annotations. If it ever came back
    empty the client would call the tool with nothing."""
    tools = {t.name: t for t in await server.list_tools()}
    schema = tools["analyze_portfolio"].input_schema

    assert "holdings" in schema["properties"]
    assert "cash" in schema["properties"]
    assert schema.get("required") == ["holdings"], (
        "cash has a default, so only holdings should be required")


# --- delegation, not reimplementation ------------------------------------


async def test_analyze_portfolio_matches_the_quant_functions_exactly():
    """The anti-duplication test. If someone reimplements the weighting here
    to 'simplify' the adapter, this fails."""
    from src.core.contracts import Holding
    from src.core import quant

    parsed = [Holding(symbol=h["symbol"], shares=h["shares"],
                      cost_basis=h["cost_basis"], asset_class=h["asset_class"])
              for h in DEV_HOLDINGS]
    expected_total, _ = quant.portfolio_value(parsed, {}, 5000.0)
    w = quant.weights(parsed, {}, 5000.0)
    expected_risk, expected_label = quant.risk_score(parsed, w)

    out = await call("analyze_portfolio", holdings=DEV_HOLDINGS, cash=5000.0)

    assert out["total_value"] == pytest.approx(round(expected_total, 2))
    assert out["risk_score"] == expected_risk
    assert out["risk_label"] == expected_label
    assert out["diversification_score"] == quant.diversification_score(parsed, w)
    assert out["concentration_flags"] == quant.concentration_flags(parsed, w)


async def test_a_concentrated_portfolio_is_flagged_through_the_protocol():
    """End to end through MCP: the flag a user would actually see."""
    out = await call("analyze_portfolio",
                     holdings=[{"symbol": "NVDA", "shares": 100, "cost_basis": 300.0}],
                     cash=0.0)

    assert out["concentration_flags"], "a single-stock portfolio raised no flag"
    assert out["total_value"] == pytest.approx(30_000.0)


async def test_a_holding_without_an_asset_class_still_gets_an_answer():
    """A model will omit optional fields. Erroring on that would be unhelpful
    where defaulting costs nothing."""
    out = await call("analyze_portfolio",
                     holdings=[{"symbol": "AAPL", "shares": 10, "cost_basis": 100.0}])

    assert out["total_value"] == pytest.approx(1000.0)
    assert "AAPL" in out["weights_pct"]


async def test_project_goal_returns_a_spread_not_a_single_forecast():
    """The spread is the honesty feature: one projection presented as a
    forecast is how tools like this mislead people."""
    out = await call("project_goal", target=200_000, current=20_000,
                     monthly=1_500, years=5, assumed_return_pct=6.0)

    from src.core.quant import project_goal

    # Round-tripped through JSON because that is what the protocol does to it:
    # project_goal returns tuples in yearly_path and they arrive as lists.
    # Comparing the raw dict fails on that alone, which says nothing useful.
    expected = json.loads(json.dumps(project_goal(200_000, 20_000, 1_500, 5, 6.0)))
    assert out == expected
    assert "scenarios" in out, "the projection shipped without its spread"
    assert len(out["scenarios"]) >= 2


async def test_price_series_statistics_match_market_calc():
    from src.core import market_calc

    prices = [100.0, 105.0, 98.0, 110.0, 103.0, 120.0]
    out = await call("analyze_price_series", prices=prices)

    assert out["points"] == 6
    assert out["period_return_pct"] == pytest.approx(
        round(market_calc.period_return(prices), 4))
    assert out["max_drawdown_pct"] == pytest.approx(
        round(market_calc.max_drawdown(prices), 4))


async def test_a_series_too_short_to_measure_says_so_rather_than_dividing_by_zero():
    out = await call("analyze_price_series", prices=[100.0])
    assert "error" in out


async def test_a_short_series_still_returns_what_it_can_support():
    """Each statistic has its own minimum - 2 points for return and drawdown,
    10 for volatility. The first version of this tool called all three for any
    series of 2 or more and raised InsufficientData straight through the
    protocol, failing the whole call. A caller asking about six points should
    get the two figures six points can justify, and be told about the third.
    """
    out = await call("analyze_price_series", prices=[100.0, 105.0, 98.0, 110.0])

    assert out["period_return_pct"] is not None
    assert out["max_drawdown_pct"] is not None
    assert out["annualised_volatility_pct"] is None
    assert "10 points" in out["note"]


async def test_correlation_refuses_a_series_too_short_to_mean_anything():
    out = await call("correlate", series_by_symbol={"AAA": [1.0, 2.0], "BBB": [2.0, 1.0]})
    assert "error" in out and "3 points" in out["error"]


async def test_correlate_returns_a_labelled_square_matrix():
    """Correlation is computed on RETURNS, not on prices.

    Worth stating, because the obvious test is wrong: a rising ramp 1..5 and
    a falling ramp 5..1 look mirrored but their RETURNS are not - both decay
    in magnitude - and they correlate at +0.81, not -1. These two series
    alternate +10%/-10% in opposite phase, which is genuinely -1.
    """
    rising = [100.0, 110.0, 99.0, 108.9, 98.01, 107.811]
    falling = [100.0, 90.0, 99.0, 89.1, 98.01, 88.209]

    out = await call("correlate", series_by_symbol={"UP": rising, "DOWN": falling})

    # Labels come back SORTED, not in insertion order - correlation_matrix
    # sorts for determinism. Index by label rather than by position.
    assert sorted(out["symbols"]) == out["symbols"] == ["DOWN", "UP"]
    at = {s: i for i, s in enumerate(out["symbols"])}
    m = out["matrix"]

    assert len(m) == 2 and len(m[0]) == 2
    assert m[at["UP"]][at["UP"]] == pytest.approx(1.0), "a series must correlate with itself"
    assert m[at["DOWN"]][at["DOWN"]] == pytest.approx(1.0)
    assert m[at["UP"]][at["DOWN"]] == pytest.approx(-1.0), (
        "opposite-phase returns must correlate at -1")
    assert m[at["UP"]][at["DOWN"]] == m[at["DOWN"]][at["UP"]], "the matrix is not symmetric"


async def test_correlate_needs_two_series_to_mean_anything():
    out = await call("correlate", series_by_symbol={"AAA": [1.0, 2.0, 3.0]})
    assert "error" in out


async def test_the_demo_personas_come_through_in_a_shape_the_other_tools_accept():
    """They are advertised as ready-made inputs, so the holdings they return
    must be loadable straight back into analyze_portfolio."""
    personas = await call("list_demo_personas")

    assert len(personas) == 6
    dev = next(p for p in personas if p["id"] == "dev")
    assert dev["holdings"]

    out = await call("analyze_portfolio", holdings=dev["holdings"], cash=dev["cash"])
    assert out["total_value"] > 0


# --- the properties that keep it safe and cheap --------------------------


async def test_no_tool_reaches_the_network_or_a_model():
    """conftest blocks sockets session-wide, so a provider call would raise.

    Running every deterministic tool here makes that a positive assertion
    rather than an absence of evidence.
    """
    await call("analyze_portfolio", holdings=DEV_HOLDINGS)
    await call("project_goal", target=1000, current=0, monthly=10, years=1)
    await call("analyze_price_series", prices=[1.0, 2.0, 3.0])
    await call("correlate", series_by_symbol={"A": [1.0, 2.0, 3.0], "B": [3.0, 2.0, 1.0]})
    await call("list_demo_personas")


async def test_a_missing_index_degrades_instead_of_killing_the_server(monkeypatch):
    """search_knowledge_base is the one tool with a heavy dependency. A broken
    index must not take the other five down with it."""
    import src.mcp_server.server as mod

    monkeypatch.setattr(mod, "_RETRIEVER", None)
    monkeypatch.setattr(mod, "_retriever",
                        lambda: (_ for _ in ()).throw(FileNotFoundError("no index")))

    out = await call("search_knowledge_base", query="what is an index fund")

    assert out["results"] == []
    assert "retrieval unavailable" in out["error"]

    # and the rest still work
    assert (await call("analyze_price_series", prices=[1.0, 2.0]))["points"] == 2


async def test_knowledge_base_search_returns_cited_passages(monkeypatch, retrieved):
    """Every passage carries its source: that is the grounding the calling
    model needs in order to cite rather than recall."""
    import src.mcp_server.server as mod
    from tests.conftest import FakeRetriever

    fake = FakeRetriever(retrieved)
    monkeypatch.setattr(mod, "_RETRIEVER", fake)

    out = await call("search_knowledge_base", query="index funds", top_k=2)

    assert len(out["results"]) == 2
    for row in out["results"]:
        assert row["source_name"] and row["source_url"], "a passage arrived uncited"
        assert row["title"] and row["text"]
    assert fake.calls[0]["top_k"] == 2


async def test_the_server_tells_the_client_these_are_education_not_advice():
    """The instructions travel with the connection. Without them the calling
    model has no reason not to present this as advice."""
    from src.mcp_server.server import INSTRUCTIONS

    assert "not" in INSTRUCTIONS.lower() and "advice" in INSTRUCTIONS.lower()
    assert server.instructions and "advice" in server.instructions.lower()
