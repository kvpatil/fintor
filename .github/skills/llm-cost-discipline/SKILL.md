---
name: llm-cost-discipline
description: 'Spend as few API credits as possible: the seven cache layers, offline mode, model tiering, the budget guard, and the rule that tests never pay'
---

Your goal is to help me build Fintor without burning API credits. The OpenAI budget is
**limited and binding**. Treat every paid call as something that must justify itself.

## Before adding any API call, ask in this order

1. **Can a cache answer it?** Check the seven layers below.
2. **Can deterministic code answer it?** Entity extraction, routing, and all arithmetic are
   regex and Python here — not LLM calls. Router tiers 1 and 2 are free by design.
3. **Does it need the strong model?** Default to the cheap tier. Escalation is explicit.
4. **Can it run offline?** If the work is UI or structural, use `FINTOR_OFFLINE=1`.

## The seven cache layers

| # | Layer | Where |
|---|---|---|
| 1 | LLM exact response | `SQLiteCache` via `set_llm_cache`, on disk |
| 2 | Semantic answer (Phase 2) | question embedding, cosine ≥0.90, with guards |
| 3 | Provider prompt cache (Phase 2) | OpenAI automatic ≥1024 tok; Anthropic explicit `cache_control` |
| 4 | Embedding cache | SQLite keyed `sha256(model‖text)` — the KB embeds once, ever |
| 5 | Market data | TTL + stale-while-error fallback |
| 6 | Retrieval (Phase 2) | query → candidate ids |
| 7 | Streamlit resources | `@st.cache_resource` singletons |

Layer 7 is not optional: without `@st.cache_resource` on the embedder and index, **every
Streamlit rerun reloads them**, which is both slow and, for hosted embeddings, expensive.

## Hard rules

- **Tests never call a paid API.** Use `FakeChatProvider` / `FakeEmbedder` from
  `tests/conftest.py`, or a recorded fixture under `tests/fixtures/`. A session fixture blocks
  `socket`, so an accidental network call fails loudly instead of billing. Never disable it.
- **Never re-embed the knowledge base.** `src/data/kb/index/` is committed for exactly this
  reason. Rebuild only when the corpus or the embedding model changes.
- **Local embeddings are the default** (`rag.embeddings: local`, model2vec, free, offline).
  The OpenAI switch is opt-in.
- **Respect the budget guard.** `src/core/cost.py` raises `BudgetExceeded` at the session
  ceiling. Do not catch and continue; surface it to the user with the remaining budget.
- **Cap output.** `llm.max_output_tokens` and prompt-level word limits are cost controls, not
  style preferences. Truncate retrieved context before the prompt, not after.

## Make cost visible

Every LLM call records provider, model, input/output tokens, USD, latency, and cache tier into
the cost meter, which the AI Internals page renders live with budget remaining. A cost that
isn't displayed is a cost nobody manages.
