# SPEC-004 — Caching, cost metering, and offline mode

## Intent

OpenAI credits are a binding constraint on this project, not a preference. This spec defines
how Fintor spends as little as possible: a provider chain that degrades instead of failing,
a cheap-by-default model tier, caching at every layer where repetition occurs, a hard session
budget with a kill switch, and an offline mode that makes the entire app runnable — including
the full LangGraph workflow — with zero network access and zero spend.

Making cost *visible* is part of the intent. A cost nobody can see is a cost nobody manages,
so every model call is metered and surfaced in the AI Internals page.

## Contract

Reads and returns `CostRecord`, `CacheTier`, `ModelTier` from `src/core/contracts.py`.
Implements `ChatProvider` and `CacheBackend` from `src/core/ports.py`.

- `src/core/config.py` — the only module permitted to read environment variables.
- `src/core/cost.py` — `CostMeter`, `BudgetExceeded`.
- `src/core/llm.py` — `OpenAIProvider`, `AnthropicProvider`, `OfflineProvider`, and the
  fallback chain that composes them.
- `src/core/cache.py` — `SqliteCache`, `MemoryCache`, `NullCache`, and the embedding cache.

## Acceptance criteria

1. A second identical completion request invokes the underlying provider **zero** times and
   returns `cache_tier == EXACT`.
2. With `FINTOR_OFFLINE=1`, a full workflow run completes while `socket` is blocked, and every
   `CostRecord` reports `usd == 0.0` and `cache_tier == OFFLINE`.
3. When the session's accumulated spend would exceed `cost.session_budget_usd`, the next call
   raises `BudgetExceeded` carrying spent and remaining amounts, and **no provider call is made**.
4. The embedding cache survives process restart: re-embedding an already-seen `(model, text)`
   pair issues no provider call.
5. When the primary provider raises, the chain returns a completion from the next provider and
   sets `fallback_used == True` on the `CostRecord`.
6. `ModelTier.CHEAP` is used unless a caller explicitly requests `STRONG`.

## Edge cases

- A cache hit must still produce a `CostRecord` (with `usd == 0`), so hit rate and savings are
  measurable rather than invisible.
- Budget exhaustion must surface to the user with the remaining budget, not be swallowed and
  retried.
- An embedding cache row whose vector length disagrees with the current model's dimension is
  skipped, never reinterpreted.
- Offline mode must be deterministic: the same question yields the same canned answer, so
  tests and demos are reproducible.

## Non-goals

- No distributed cache. SQLite on local disk is correct for a single-instance Streamlit app;
  Cloud Run's statelessness is handled at deploy time, not here.
- No token-level budget enforcement mid-stream. The guard is checked before a call, not during.
- Semantic caching (layer 2) and provider prompt caching (layer 3) are Phase 2.

## Status

Draft — implementation follows this commit.
