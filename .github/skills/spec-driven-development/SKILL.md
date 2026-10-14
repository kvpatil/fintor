---
name: spec-driven-development
description: 'The spec-first workflow for Fintor: spec file format, numbered acceptance criteria, commit discipline, and the traceability matrix'
---

Your goal is to help me develop Fintor spec-first, so that the process is **demonstrable from
git history and a traceability matrix** rather than asserted in a README.

## The workflow, in order

1. **Write the spec** as `specs/NNN-name.md` using the format below.
2. **Commit the spec on its own** — `docs(spec): add SPEC-00N <name>`.
3. **Implement** against it.
4. **Commit the implementation referencing the spec ID** — `feat(router): SPEC-002 tiers 1-2`.
5. **Add or update the test** that proves each acceptance criterion, and record it in
   `specs/traceability.md`.

Never implement first and backfill the spec. The ordering is the artifact; a spec written
afterwards proves nothing.

## Spec format

```markdown
# SPEC-00N — <name>

## Intent
One paragraph: what this enables and why, in product terms.

## Contract
The Pydantic models in `src/core/contracts.py` this reads and returns. Reference them by
name — do not restate their fields here.

## Acceptance criteria
1. Numbered, singular, and **executable** — each maps to exactly one test.
2. Written as an observable assertion, not a description of the implementation.

## Edge cases
What must not break, and what the defined behaviour is when it does.

## Non-goals
What this deliberately does not do, so scope creep is visible in review.

## Status
Draft | Implemented | Verified — plus the test names that verify it.
```

## Writing good acceptance criteria

- **Observable, not procedural.** "Candidates scoring below threshold produce a refusal with
  no LLM call" — not "the gate filters the list".
- **One assertion each.** If a criterion needs "and", it is two criteria.
- **Include the negative case.** What must *not* happen is usually the criterion worth having:
  no LLM call, no network access, no silent fallback, no duplicate disclaimer.
- **Name the failure mode** for edge cases, so the test asserts a specific exception or value
  rather than merely "handles gracefully".

## Traceability

`specs/traceability.md` holds one row per acceptance criterion: spec ID → criterion → test
name → status. A criterion with no test is `Draft`, never `Implemented`. Regenerate the table
in the same change as the test, per the docs-with-code convention.

## Architecture criteria are testable too

Structural rules get specs and tests like anything else — `test_no_upward_imports` enforces the
dependency direction from [copilot-instructions](../../copilot-instructions.md) by walking each
module's AST. When a structural rule is violated, fix the design, never the test.
