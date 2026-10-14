# SPEC-005 — Personas and personalization

## Intent

The brief's business case calls for "personalized learning paths… adapts to each user's
knowledge level, goals, and risk tolerance." A persona selector makes that demonstrable: the
same six agents over the same corpus produce materially different answers because the reader
is different. No login gate — switching is instant, which is better for a demo than an auth
wall.

## Contract

`Persona`, `Holding`, `Goal`, `Difficulty` from `src/core/contracts.py`.
`src/data/personas.py` holds six synthetic profiles and `get(persona_id)`.

## Acceptance criteria

1. A persona's `thread_id` is stable, derived from its id, and unique across personas.
2. The active persona's `experience_level` is injected into every agent's system prompt.
3. Retrieval for a beginner persona returns only beginner-difficulty passages; an advanced
   persona may draw on the whole corpus.
4. Each persona accumulates its own entry in the cost meter's per-persona ledger.
5. Every persona is labelled as a teaching example wherever its portfolio is shown.
6. The six personas produce visibly different computed risk and diversification scores, so the
   selector demonstrably changes the analysis rather than only the name.

## Edge cases

- A persona with no holdings (Maya) must render a useful page, not an error.
- An unknown persona id resolves to `None` and the app falls back to general answers.
- Crypto holdings must be priced through the same chain as equities, or excluded honestly.

## Non-goals

- No real accounts, no brokerage linkage, no authentication.
- Cross-session preference learning is Phase 3 (long-term vector memory).

## Status

Implemented — `src/data/personas.py`, prompt conditioning in `src/agents/base.py`,
difficulty filtering in `src/rag/retriever.py`, per-persona threads in `src/workflow/graph.py`.

Verified by hand and in the Streamlit page probes: computed profiles span risk 10–90 and
diversification 18–86 across the six personas; a beginner ceiling returns only beginner
passages while an unfiltered query surfaces `Duration (advanced)` first. Formalised as
`test_persona_conditions_prompt_and_filters_difficulty` in Phase 2.
