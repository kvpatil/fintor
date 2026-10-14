# SPEC-003 — LangGraph orchestration

## Intent

One question may need several specialists, and they should run concurrently rather than in
sequence. This spec defines the graph: a guard that runs before anything costs money, a router,
dynamic fan-out to the selected agents, a tool-calling loop for live market data, deterministic
synthesis, and a verification pass over citations. Conversation state is durable, so a thread
survives a restart.

## Contract

Reads `Query`, `RouteDecision`, `Persona`; produces `AgentResult` list and a final answer dict.
`WorkflowState` is a `TypedDict` whose `agent_results` field carries an `operator.add` reducer.

- `src/workflow/graph.py` — the `StateGraph`.
- `src/workflow/tools.py` — `@tool` market functions, `bind_tools`, `ToolNode`, loop-back.

## Acceptance criteria

1. A compound question fans out to more than one agent, and both results appear in
   `agent_results` — proving the reducer merges concurrent writes.
2. Agents in a fan-out run concurrently: wall-clock for two slow agents is materially less
   than their sum.
3. Citations are renumbered across agents so two agents' `[1]` markers do not collide.
4. The tool loop terminates: a tool-calling turn is followed by a tool result and then a final
   answer, and the loop cannot exceed `workflow.max_tool_iterations`.
5. Self-harm input short-circuits before the router and before any LLM call, returning the
   deterministic crisis response, and is not persisted.
6. A thread resumed by `thread_id` after a process restart still carries its history.
7. One agent raising does not fail the request; its section is replaced by an explanation.

## Edge cases

- An agent timeout degrades to an error result rather than hanging the graph.
- An empty intent list defaults to `finance_qa`.
- The graph must compile with no checkpointer (tests) and with one (the app).

## Non-goals

- No reflection/critique cycle yet; that is SPEC-006 (Phase 2).
- No human-in-the-loop interrupts.

## Status

Draft — implementation follows this commit.
