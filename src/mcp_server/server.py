"""Fintor's finance tools, exposed over the Model Context Protocol.

    .venv/bin/python -m src.mcp_server          # stdio, for Claude Desktop

WHAT THIS IS AND IS NOT. It is a thin adapter: every tool here delegates to a
function in `src/core/quant.py`, `src/core/market_calc.py` or `src/rag/`, all
of which are already unit-tested. No finance logic lives in this file, because
logic that lives only behind a protocol boundary is logic nobody can test
without the protocol.

WHY NO LLM. None of these tools calls a model. The client - Claude Desktop -
is the model; handing it a second one would be paying twice to get a worse
answer. So the server needs no API key and makes no outbound request, which
also means it cannot run up a bill while sitting in someone's config file.

The one exception is `search_knowledge_base`, which loads the committed
retrieval index. That is a local file plus a local embedding model, still no
network, and it is built LAZILY so the server starts instantly and the other
tools work even if the index is missing.

Tool results are plain dicts. The MCP SDK serialises them to JSON, and a dict
of named numbers survives a model reading it far better than prose does.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from src.core import market_calc, quant
from src.core.contracts import Holding

INSTRUCTIONS = """Fintor exposes finance EDUCATION tools: portfolio analysis,
goal projection and price-series statistics, computed in Python rather than
estimated by a model.

These tools explain and compute. They do not give personal financial,
investment, legal or tax advice, and they do not recommend buying or selling
anything. Present their output as education, and say that figures are
illustrative."""

server = MCPServer("fintor", instructions=INSTRUCTIONS)


def _holdings(rows: list[dict[str, Any]]) -> list[Holding]:
    """Accept the loose JSON a model will send and make real Holdings.

    `asset_class` defaults rather than raising: a model that omits it should
    get an answer about the rest of the portfolio, not an error.
    """
    out = []
    for row in rows:
        out.append(Holding(
            symbol=str(row["symbol"]).upper(),
            shares=float(row["shares"]),
            cost_basis=float(row.get("cost_basis", 0.0)),
            asset_class=str(row.get("asset_class", "equity")),
        ))
    return out


@server.tool()
def analyze_portfolio(holdings: list[dict[str, Any]], cash: float = 0.0) -> dict[str, Any]:
    """Analyse a portfolio: total value, weights, diversification, risk and
    concentration flags.

    Each holding is {"symbol", "shares", "cost_basis", "asset_class"}.
    Valued at cost basis - this tool takes no live prices, so the numbers are
    illustrative rather than a current statement.
    """
    parsed = _holdings(holdings)
    total, unpriced = quant.portfolio_value(parsed, {}, cash)
    w = quant.weights(parsed, {}, cash)
    risk, risk_label = quant.risk_score(parsed, w)
    return {
        "total_value": round(total, 2),
        "cash": round(cash, 2),
        "weights_pct": {k: round(v, 2) for k, v in w.items()},
        "class_weights_pct": {k: round(v, 2)
                              for k, v in quant.class_weights(parsed, w).items()},
        "diversification_score": quant.diversification_score(parsed, w),
        "risk_score": risk,
        "risk_label": risk_label,
        "concentration_flags": quant.concentration_flags(parsed, w),
        "valued_at_cost_basis": unpriced,
        "disclaimer": "Education, not advice. Figures are illustrative.",
    }


@server.tool()
def project_goal(target: float, current: float, monthly: float, years: float,
                 assumed_return_pct: float = 6.0) -> dict[str, Any]:
    """Project a savings goal, with a spread either side of the assumed return.

    The spread is the point: a single projection presented as a forecast is
    the most common way a tool like this misleads people.
    """
    return quant.project_goal(target, current, monthly, years, assumed_return_pct)


@server.tool()
def analyze_price_series(prices: list[float], periods_per_year: int = 252) -> dict[str, Any]:
    """Period return, maximum drawdown and annualised volatility for a series
    of closing prices.

    Max drawdown is included because it describes the experience of holding
    something better than volatility does.
    """
    if len(prices) < 2:
        return {"error": "need at least two prices"}
    series = [float(p) for p in prices]
    out: dict[str, Any] = {
        "points": len(series),
        "period_return_pct": round(market_calc.period_return(series), 4),
        "max_drawdown_pct": round(market_calc.max_drawdown(series), 4),
    }
    # Each statistic has its own data minimum (2, 2, and 10 points) and
    # market_calc raises rather than returning a number it cannot support.
    # Compute what the series can carry and SAY what it cannot, instead of
    # failing the whole call - a caller asking about a short series should
    # still get its return and drawdown.
    if len(series) >= 10:
        out["annualised_volatility_pct"] = round(
            market_calc.volatility(series, periods_per_year), 4)
    else:
        out["annualised_volatility_pct"] = None
        out["note"] = "volatility needs at least 10 points"
    return out


@server.tool()
def correlate(series_by_symbol: dict[str, list[float]]) -> dict[str, Any]:
    """Correlation matrix across several price series.

    Allocation says what you own; correlation says whether it moves together.
    Diversification comes from the second, not the first.
    """
    if len(series_by_symbol) < 2:
        return {"error": "need at least two series"}
    cleaned = {k: [float(x) for x in v] for k, v in series_by_symbol.items()}
    too_short = sorted(k for k, v in cleaned.items() if len(v) < 3)
    if too_short:
        return {"error": f"correlation needs at least 3 points per series; "
                         f"too short: {', '.join(too_short)}"}
    labels, matrix = market_calc.correlation_matrix(cleaned)
    return {"symbols": labels,
            "matrix": [[round(c, 4) for c in row] for row in matrix]}


@server.tool()
def list_demo_personas() -> list[dict[str, Any]]:
    """The six synthetic readers Fintor ships with.

    Useful as ready-made inputs for the other tools. They are teaching
    examples, not real accounts.
    """
    from src.data.personas import PERSONAS

    return [{
        "id": p.id,
        "name": p.name,
        "age": p.age,
        "headline": p.headline,
        "experience_level": p.experience_level.value,
        "risk_tolerance": p.risk_tolerance,
        "horizon_years": p.horizon_years,
        "cash": p.cash,
        "holdings": [{"symbol": h.symbol, "shares": h.shares,
                      "cost_basis": h.cost_basis, "asset_class": h.asset_class}
                     for h in p.holdings],
    } for p in PERSONAS]


@server.tool()
def search_knowledge_base(query: str, top_k: int = 5,
                          category: str | None = None) -> dict[str, Any]:
    """Search Fintor's cited finance glossary and return passages with sources.

    This is the grounding the rest of the product runs on: every passage
    carries the source it came from, so the calling model can cite rather
    than recall.
    """
    try:
        retriever = _retriever()
    except Exception as exc:  # noqa: BLE001 - a missing index must not kill the server
        return {"error": f"retrieval unavailable: {type(exc).__name__}: {exc}",
                "results": []}

    chunks = retriever.retrieve(query, top_k=top_k, category=category)
    return {
        "query": query,
        "results": [{
            "title": c.title,
            "text": c.text,
            "category": c.category,
            "difficulty": c.difficulty,
            "source_name": c.source_name,
            "source_url": c.source_url,
            "score": round(c.score, 4),
        } for c in chunks],
    }


_RETRIEVER = None


def _retriever():
    """Built on first use, then kept.

    Lazy on purpose: loading the embedding model at import would make the
    server slow to start and would break every other tool if the index were
    missing. Nothing here touches the network - the index is committed and
    the embedding model is local.
    """
    global _RETRIEVER
    if _RETRIEVER is None:
        from src.container import build_retriever

        _RETRIEVER = build_retriever()
    return _RETRIEVER


def main() -> None:
    """Serve over stdio, which is the transport Claude Desktop speaks."""
    server.run()


if __name__ == "__main__":
    main()
