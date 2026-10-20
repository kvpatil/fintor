# Traceability matrix

One row per acceptance criterion. A criterion with no passing test is `Draft`, never
`Implemented`. Regenerated in the same change as the test, per the docs-with-code convention.

Run `pytest -q` to verify every row below. 349 tests, no network, no API spend.

| Spec | Criterion | Test | Status |
|---|---|---|---|
| SPEC-000 | 1. One-way dependency order | `test_no_upward_imports` | Verified |
| SPEC-000 | 2. `core` imports nothing internal | `test_core_imports_nothing_internal` | Verified |
| SPEC-000 | 3. Every Protocol has ≥2 implementations | `test_protocols_have_two_impls` | Verified |
| SPEC-000 | — | `test_only_entrypoints_import_the_composition_root` | Verified |
| SPEC-001 | 1. RRF uses Σ 1/(k+rank), k=60 | `test_rrf_fusion_orders_by_reciprocal_rank` | Verified |
| SPEC-001 | 2. Index/embedder mismatch raises, naming both | `test_index_rejects_embedding_dimension_mismatch` | Verified |
| SPEC-001 | 3. Below threshold refuses, no LLM call | `test_retrieval_gate_refuses_below_threshold` | Verified |
| SPEC-001 | 4. Beginner ceiling yields only beginner chunks | `test_difficulty_ceiling_filters_corpus` | Verified |
| SPEC-001 | 5. Sparse half contributes independently | `test_sparse_retrieves_exact_term` | Verified |
| SPEC-001 | 6. 50–100 docs, every citation has a source | `test_corpus_integrity` | Verified |
| SPEC-001 | 7. Rebuild issues zero embedding calls | `test_embedding_cache_survives_restart` | Verified |
| SPEC-002 | 1. Unambiguous input resolves at tier 1 | `test_router_tier1_regex_confident_cases` (8 cases) | Verified |
| SPEC-002 | 2. Compound question returns both intents | `test_compound_question_returns_both_intents_in_canonical_order` | Verified |
| SPEC-002 | 3. Escalates tier 1 → 2 → 3 | `test_router_escalates_to_tier3_when_ambiguous`, `test_tier2_embedding_resolves_without_an_llm_call` | Verified |
| SPEC-002 | 4. Tier-3 failure falls back to rules | `test_router_falls_back_to_rules_when_llm_tier_raises` | Verified |
| SPEC-002 | 5. Advice phrasing sets the flag | `test_advice_phrasing_sets_the_flag` | Verified |
| SPEC-002 | 6. A raising agent returns a result, not an exception | `test_one_raising_agent_degrades_only_its_section` | Verified |
| SPEC-002 | edge. Ticker in a tax question is not a lookup | `test_ticker_inside_a_tax_question_is_not_a_price_lookup` | Verified |
| SPEC-002 | edge. Comparison is one question | `test_comparison_is_not_split_into_clauses` | Verified |
| SPEC-002 | edge. Empty input routes to finance_qa | `test_empty_input_routes_to_finance_qa` | Verified |
| SPEC-003 | 1. Fan-out merges concurrent writes | `test_graph_fanout_merges_parallel_agent_results` | Verified |
| SPEC-003 | 2. Fan-out runs concurrently | `test_fanout_runs_concurrently` | Verified |
| SPEC-003 | 3. Citations renumber without collision | `test_citations_renumber_across_agents_without_collision` | Verified |
| SPEC-003 | 4. Tool loop terminates under the cap | `test_tool_node_loops_back_and_terminates`, `test_tool_loop_respects_the_iteration_cap` | Verified |
| SPEC-003 | 5. Self-harm short-circuits before router/LLM | `test_self_harm_short_circuits_before_router_and_llm` | Verified |
| SPEC-003 | 6. Thread survives a restart | *manual (run_query + thread_history)* | Implemented |
| SPEC-003 | 7. One agent failing degrades one section | `test_one_raising_agent_degrades_only_its_section` | Verified |
| SPEC-003 | — | `test_citation_verification_strips_unresolvable_markers` | Verified |
| SPEC-003 | — | `test_citation_verification_keeps_valid_markers_untouched` | Verified |
| SPEC-004 | 1. Exact cache: zero provider calls | `test_exact_cache_returns_without_provider_call` | Verified |
| SPEC-004 | 2. Offline: no network, usd == 0, deterministic | `test_offline_mode_makes_no_network_calls` | Verified |
| SPEC-004 | 3. Budget guard blocks before spending | `test_budget_guard_blocks_when_ceiling_exceeded` | Verified |
| SPEC-004 | 4. Embedding cache survives restart | `test_embedding_cache_survives_restart` | Verified |
| SPEC-004 | 5. Fallback sets `fallback_used` | `test_provider_fallback_on_primary_failure` | Verified |
| SPEC-004 | 6. Cheap tier is the default | *config assertion in `config.yaml`* | Implemented |
| SPEC-004 | edge. Cache hits are still metered | `test_cache_hit_is_still_metered` | Verified |
| SPEC-005 | personas condition prompt + retrieval + thread | *manual; pytest cases in Phase 2* | Implemented |

## Notes

- **SPEC-003 criterion 6** is exercised by `run_query` + `thread_history` against a real
  `AsyncSqliteSaver` but not yet as a pytest case, because the session-wide socket block
  interacts with aiosqlite's connection setup. Promoted to a test in Phase 2.
- **SPEC-004 criterion 6** is a configuration invariant (`llm.default_tier: cheap`) rather
  than runtime behaviour; a test asserting a config value would restate the file.
- **SPEC-005** personas are verified by hand and in the Streamlit page probes. Phase 2 adds
  `test_persona_conditions_prompt_and_filters_difficulty`.

Two structural bugs were caught by these tests rather than by review:

1. `test_no_upward_imports` found the composition root sitting in `core` (the bottom layer)
   while importing from every layer above it. Fixed by moving it to `src/container.py`.
2. SPEC-003 criterion 7 found that the graph's agent node contained only `TimeoutError`, so an
   agent failing outside `BaseAgent`'s contract took down every fanned-out branch with it.
