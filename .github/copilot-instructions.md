# Fintor

Multi-agent AI **finance assistant**: six specialist agents answer money questions in plain
English, grounded in a cited knowledge base, with live market data and persona-driven
personalization. It explains; it does not give personal financial, investment, legal or tax
advice, and every answer says so.

## Stack & layout
- **App**: Streamlit multipage app (`src/web_app/app.py`), `st.navigation` with two groups
  (Workspace, About Fintor). Pages live in `src/web_app/pages/`.
- **Orchestration**: LangGraph `StateGraph` in `src/workflow/graph.py` — `guard → router →
  Send(fan-out) → agent ⇄ tools → critic → synthesize → verify`. Durable threads via
  `SqliteSaver`. Routing in `src/workflow/router.py`, tools in `src/workflow/tools.py`.
- **Agents**: six specialists in `src/agents/` (finance_qa, portfolio, market, goal_planning,
  news, tax), each subclassing `BaseAgent` and implementing only `_execute`.
- **Retrieval**: `src/rag/` — model2vec local embeddings (no torch) or OpenAI, `NumpyIndex`
  exact cosine, `rank_bm25` sparse, fused with Reciprocal Rank Fusion at k=60.
- **LLM**: OpenAI primary, Anthropic fallback, via LangChain `.with_fallbacks()` in
  `src/core/llm.py`. Cheap tier by default; strong tier only on explicit escalation.
- **Data**: `src/data/` — yfinance quotes/history and yfinance+RSS news, both **keyless**.
  Personas in `src/data/personas.py`.
- **Deploy**: Docker + GCP Cloud Run (`deploy/`).

## Architecture rules
- **Dependency direction is one-way**: `web_app → workflow → agents → {rag, data} → core`.
  `core` imports nothing internal. `tests/test_architecture.py::test_no_upward_imports`
  fails the build if this is violated — fix the design, never the test.
- **Every external dependency sits behind a `typing.Protocol`** in `src/core/ports.py`
  (`Embedder`, `VectorIndex`, `Retriever`, `ChatProvider`, `CacheBackend`,
  `MarketDataProvider`, `NewsProvider`). Each has at least two implementations.
- **All wiring happens in `src/core/container.py`**, driven by `config.yaml`. No module
  constructs its own dependencies, and nothing reads environment variables outside
  `src/core/config.py`.
- **Cross-layer data shapes are Pydantic models in `src/core/contracts.py`** — never raw
  dicts across a boundary.
- **No business logic in Streamlit pages.** Pages render and call into `workflow`.

## Always-on conventions
- **Education, not advice**: never produce buy/sell recommendations, price predictions, or a
  personal tax calculation. See [finance-compliance](skills/finance-compliance/SKILL.md).
- **Spec before code**: no implementation without a spec in `specs/` carrying numbered
  acceptance criteria, and a test referencing it. Commit the spec first; put the spec ID in
  the implementation commit. See [spec-driven-development](skills/spec-driven-development/SKILL.md).
- **Cost discipline**: OpenAI credits are a binding constraint, not a preference. Check the
  cache before adding a call; never call a paid API from a test. See
  [llm-cost-discipline](skills/llm-cost-discipline/SKILL.md).
- **Docs with code**: update `README.md`, `docs/design.md`, and affected specs in the same
  change as the code — never defer. Prefer linking over duplicating.
- **Gitignore generated state at creation time**: when you introduce local runtime state,
  caches, or generated artifacts, add the matching `.gitignore` entry in the same change.
  Already covered: `data/cache/`, `data/checkpoints/`, `data/market/`, `.venv/`.
  Deliberate exception — `src/data/kb/index/` **is** committed, so graders and Cloud Run
  never re-embed.
- **Comments explain *why*, not *what*.** Never add a comment restating the next line.

Task- and file-scoped guidance lives in `.github/instructions/`, `.github/agents/`, and
`.github/skills/` and is applied automatically.
