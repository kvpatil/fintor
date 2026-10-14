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
