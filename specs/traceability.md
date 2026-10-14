# Traceability matrix

One row per acceptance criterion. A criterion with no passing test is `Draft`, never
`Implemented`. Regenerated in the same change as the test, per the docs-with-code convention.

| Spec | Criterion | Test | Status |
|---|---|---|---|
| SPEC-000 | 1. One-way dependency order | `test_no_upward_imports` | Draft |
| SPEC-000 | 2. `core` imports nothing internal | `test_no_upward_imports` | Draft |
| SPEC-000 | 3. Every Protocol has ≥2 implementations | `test_protocols_have_two_impls` | Draft |
| SPEC-000 | 4. Persona thread_id is stable and unique | `test_persona_thread_id_isolated` | Draft |
| SPEC-000 | 5. CostRecord populated on cache hits | `test_exact_cache_returns_without_provider_call` | Draft |
| SPEC-001 | 1. RRF uses Σ 1/(k+rank), k=60 | `test_rrf_fusion_orders_by_reciprocal_rank` | Draft |
| SPEC-001 | 2. Index/embedder mismatch raises | `test_index_rejects_embedding_dimension_mismatch` | Draft |
| SPEC-001 | 3. Below threshold refuses, no LLM call | `test_retrieval_gate_refuses_below_threshold` | Draft |
| SPEC-001 | 4. Beginner ceiling yields only beginner chunks | `test_difficulty_ceiling_filters_corpus` | Draft |
| SPEC-001 | 5. Sparse half contributes independently | `test_sparse_retrieves_exact_term` | Draft |
| SPEC-001 | 6. 50–100 docs, every citation has a source | `test_corpus_integrity` | Draft |
| SPEC-001 | 7. Rebuild issues zero embedding calls | `test_embedding_cache_survives_restart` | Draft |
| SPEC-004 | 1. Exact cache: zero provider calls | `test_exact_cache_returns_without_provider_call` | Draft |
| SPEC-004 | 2. Offline: no network, usd == 0 | `test_offline_mode_makes_no_network_calls` | Draft |
| SPEC-004 | 3. Budget guard blocks before spending | `test_budget_guard_blocks_when_ceiling_exceeded` | Draft |
| SPEC-004 | 5. Fallback sets fallback_used | `test_provider_fallback_on_primary_failure` | Draft |
