# SPEC-002 — Three-tier routing and the six agents

## Intent

A question must reach the right specialist, and most questions can be routed without spending
anything. Routing therefore escalates through three tiers: deterministic rules, then embedding
similarity against intent centroids, then an LLM classifier with structured output. Tiers one
and two are free, so the LLM is consulted only for genuinely ambiguous input.

A question may legitimately need several specialists ("how are capital gains taxed and how is
SPY doing?"), so routing is multi-label.

## Contract

Returns `RouteDecision` with `intents`, `tier`, `reason`, `advice_request`, `confident`.
Agents return `AgentResult`. Both from `src/core/contracts.py`.

- `src/workflow/router.py` — `Router` with the three tiers.
- `src/agents/base.py` — `BaseAgent`: timing, cost collection, error containment.
- `src/agents/{finance_qa,tax,portfolio,market,goal_planning,news}.py`.
- `src/agents/registry.py` — intent → agent.

## Acceptance criteria

1. Unambiguous questions resolve at tier 1 with `tier == RULES` and no model call.
2. A compound question naming two domains returns both intents, in canonical order.
3. When tier 1 is not confident, tier 2 runs; when tier 2 is also inconclusive, tier 3 runs.
4. If tier 3 raises, the decision falls back to the tier-1 result with
   `tier == LLM_FALLBACK_RULES`, and routing never propagates the error.
5. Advice-seeking phrasing sets `advice_request = True` regardless of which tier resolved it.
6. An agent that raises returns an `AgentResult` carrying `error_code`, never an exception.
7. Every agent populates `latency_ms` and appends any `CostRecord`s it incurred.

## Edge cases

- A ticker inside a tax question must not route to the market agent.
- "What is the difference between X and Y" is one comparison, not two clauses.
- Empty or whitespace-only input routes to `finance_qa` rather than failing.

## Non-goals

- No agent-to-agent delegation; the graph fans out, agents do not call each other.
- Reflection and critique are SPEC-006 (Phase 2).

## Status

Draft — implementation follows this commit.
