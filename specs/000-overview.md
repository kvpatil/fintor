# SPEC-000 — Architecture & contracts

## Intent

Fintor is a multi-agent AI finance assistant. Six specialist agents answer money questions in
plain English, grounded in a cited knowledge base, enriched with keyless live market data,
and conditioned on a selectable synthetic persona. This spec fixes the structural rules that
every later spec depends on, so that modularity is enforced mechanically rather than by
convention: a one-way dependency rule, a single set of cross-boundary data shapes, and a
Protocol for every external dependency.

## Contract

`src/core/contracts.py` holds every shape permitted to cross a layer boundary: `Persona`,
`Holding`, `Goal`, `Query`, `RouteDecision`, `RetrievedChunk`, `Citation`, `AgentResult`,
`CostRecord`, `Quote`, `NewsItem`, plus the `Intent`, `RouterTier`, `Difficulty`,
`ModelTier`, `CacheTier`, and `DataStatus` enumerations.

`src/core/ports.py` holds the Protocols: `Embedder`, `VectorIndex`, `Retriever`,
`ChatProvider`, `CacheBackend`, `MarketDataProvider`, `NewsProvider`.

## Acceptance criteria

1. No module imports from a layer above it in the order
   `web_app → workflow → agents → {rag, data} → core`.
2. `src/core/*` imports nothing from `src.agents`, `src.rag`, `src.data`, `src.workflow`, or
   `src.web_app`.
3. Every Protocol in `ports.py` has at least two concrete implementations in the repo.
4. A `Persona` exposes a stable `thread_id` derived from its id, so checkpointer threads
   cannot collide between personas.
5. `CostRecord` is populated for every model call, including cache hits, where `usd == 0`
   and `cache_tier != MISS`.

## Edge cases

- A new module placed in the wrong layer must fail `test_no_upward_imports` with the
  offending module and import named, not merely a boolean assertion failure.
- Circular imports between sibling modules in the same layer are permitted by the dependency
  rule but are still a design smell; prefer moving the shared shape into `contracts.py`.

## Non-goals

- No dependency-injection framework. Wiring is plain Python in `core/container.py`.
- No runtime enforcement of the dependency rule; it is a build-time test, so it costs nothing
  in production.

## Status

Implemented — `contracts.py`, `ports.py`. Verified by `test_no_upward_imports` (Block B).
