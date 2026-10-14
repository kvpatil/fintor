# Fintor — design document

Multi-agent AI finance **tutor**. Six specialist agents answer money questions in plain
English, grounded in a cited knowledge base, enriched with keyless live market data, and
conditioned on a selectable synthetic persona. It explains; it does not advise.

---

## 1. Goals and principles

| Principle | Consequence in the code |
|---|---|
| **Code computes, the model explains** | Every figure originates in `src/core/quant.py` or a provider payload. Narration is checked against those facts and discarded whole if it introduces a number. |
| **Education, not advice** | No buy/sell output, no price predictions, no personal tax computation. One disclaimer, appended idempotently. |
| **Refuse rather than guess** | A relevance floor runs *before* the LLM. Nothing clears it → no model call at all. |
| **Make the machinery visible** | Routing tier, retrieval ranks, cache tier, token cost, and guardrail results are all rendered in the AI Internals page. |
| **Cost is a design constraint** | Seven cache layers, a cheap-by-default model tier, a hard session budget, and an offline mode that runs the whole app for free. |
| **Modularity enforced, not requested** | A one-way dependency rule with a build-time fitness test; every external dependency behind a Protocol. |

---

## 2. Architecture

### 2.1 Workflow graph

Generated from the compiled graph via `compiled.get_graph().draw_mermaid()`, so it cannot
drift from the code. The in-app **Architecture** page renders the live version.

```mermaid
flowchart TD
  __start__([start]) --> guard
  guard -.->|normal| router
  guard -.->|crisis short-circuit| synthesize
  router -.->|Send fan-out| agent
  router -.->|no agents| synthesize
  agent --> synthesize
  synthesize --> verify
  verify --> __end__([end])
```

`agent` is **one reusable node**. Fan-out is dynamic via `Send()`, one payload per planned
agent, and `agent_results` carries an `operator.add` reducer. Without that reducer, concurrent
branches would overwrite each other and only the last one home would survive — which is the
single most important thing to understand about parallel state in LangGraph.

### 2.2 System layers

```mermaid
flowchart TB
  U["web_app<br/>Streamlit pages, persona selector"] --> W["workflow<br/>graph · router · tools · verify"]
  W --> A["agents<br/>6 specialists · narration"]
  A --> R["rag<br/>retriever · index · embeddings · categories"]
  A --> D["data<br/>market · news · personas · corpus"]
  R --> C["core<br/>ports · contracts · llm · cache · cost · quant · safety"]
  D --> C
  C --> X["OpenAI · Yahoo Finance · RSS"]
  CR["container<br/>composition root"] -.->|wires everything| C
```

### 2.3 Dependency rule

```mermaid
flowchart LR
  web_app --> workflow --> agents --> rag --> core
  agents --> data --> core
```

Strictly one-way. `tests/test_architecture.py::test_no_upward_imports` walks every module's
AST and fails the build on a violation. It caught a real inversion on day one: the composition
root was sitting in `core`, the bottom layer, while importing from every layer above it. Fixed
by moving it to `src/container.py`, with a second test asserting that only entry points import
it.

### 2.4 Retrieval pipeline

```mermaid
flowchart LR
  Q[Question] --> E[Embed 256-d]
  Q --> B[BM25 tokenize]
  E --> DN[Dense top-20]
  B --> SP[Sparse top-20]
  DN --> F["RRF fuse k=60"]
  SP --> F
  F --> CO[Recompute cosine]
  CO --> FL["Difficulty + category filter<br/>(from persona)"]
  FL --> G{"cosine ≥ 0.25?"}
  G -->|no| REF["Refuse — no LLM call"]
  G -->|yes| P["Numbered passages → LLM"]
  P --> V["Verify every [n]"]
```

**Why RRF rather than a weighted score blend.** Cosine similarity and BM25 relevance live on
different, un-normalizable scales. Any weighted sum needs arbitrary constants that silently
shift as the corpus changes. RRF uses only *rank*, which is comparable by construction. The
true cosine is then recomputed on the fused set, because an RRF score says nothing about
whether the top hit is actually relevant — it only says it was ranked highly by something.

### 2.5 Caching and cost control

```mermaid
flowchart TB
  A[Request] --> BG{Budget remaining?}
  BG -->|no| KILL["BudgetExceeded<br/>kill switch, no call made"]
  BG -->|yes| L1{"Layer 1: exact response?"}
  L1 -->|hit| Z["Return — 0 tokens, still metered"]
  L1 -->|miss| L4{"Layer 4: embedding cached?"}
  L4 -->|hit| SKIP[No embedding call]
  L4 -->|miss| EMB[Embed once, persist]
  SKIP --> PRV[Provider call]
  EMB --> PRV
  PRV --> REC[Record CostRecord]
```

### 2.6 Persona conditioning

```mermaid
flowchart LR
  PS[Persona selected] --> PP["Prompt preamble<br/>experience level, risk, horizon"]
  PS --> DC["Difficulty ceiling<br/>corpus pre-filter"]
  PS --> TH["thread_id<br/>isolated checkpoint"]
  PS --> LED["Per-persona cost ledger"]
  PP --> ANS[Answer]
  DC --> ANS
  TH --> ANS
```

---

## 3. Component design

### 3.1 Three-tier router

| Tier | Mechanism | Cost | When it runs |
|---|---|---|---|
| 1 | Regex signal banks per intent, clause-split, multi-label | free | always |
| 2 | Query embedding vs. per-intent centroids built from exemplar phrases | free | tier 1 not confident |
| 3 | LLM classifier with Pydantic structured output | paid | tiers 1–2 inconclusive |

Two rules worth noting. A **comparison is not split into clauses**, so "difference between an
ETF and a mutual fund" stays one question instead of becoming two half-answers. And a ticker
inside a tax question is suppressed as a price lookup **only when both signals fired in the
same clause** — so "how are capital gains taxed and how is SPY doing?" correctly fans out to
two agents, while "what tax do I pay on my NVDA shares?" does not.

Tier 2 requires both a similarity floor and a **margin over the runner-up**: a query sitting
equally close to two centroids is ambiguous no matter how high the top score is.

Routing never raises. A tier-3 failure returns the tier-1 result tagged
`llm_fallback_rules` — failing to route is not a reason to fail to answer.

### 3.2 The six agents

| Agent | Distinct mechanism |
|---|---|
| `finance_qa` | The RAG agent. Gate → numbered passages → cited answer. Its prompt now says to **stop** rather than continue uncited, after a live run showed it filling a gap from model recall. |
| `tax` | Subclass of `finance_qa`: stricter prompt, corpus scoped to the **tax group** (not one raw category — "What is an HSA?" is a tax question whose passage lives under `retirement`), plus a personal-tax redirect applied after the answer so it appears exactly once. |
| `portfolio` | Zero LLM arithmetic. `quant.py` computes value, weights, HHI-based effective positions, diversification and risk scores, concentration flags; the model only narrates. |
| `market` | Deterministic entity extraction instead of tool-arg guessing; index names map to ETF proxies and the substitution is disclosed. |
| `goal_planning` | The only agent with an LLM extractor, behind a hard verifier: any numeric field whose value does not appear literally in the user's message is dropped. Every field is optional so "nothing extracted" is a valid outcome. |
| `news` | Headlines treated as untrusted third-party text. Sample headlines are **never narrated** — a model paraphrasing placeholder news reads as real reporting. |

### 3.3 Grounding

`agents/narration.py` hands the model a FACTS payload and then checks the prose it returns.
Every significant figure (`$`, `%`, `k/M/B`, or a bare number ≥1000 that is not a year) must
be within tolerance of a number in the payload. Tolerances cover display rounding — `$29,300`
for `29300.0`, or `$29,000` as a thousands rounding — but not invention. One ungrounded figure
discards the **whole** narration and substitutes the deterministic template, recorded as
`narration="template"` so the swap is visible rather than silent.

This is a programmatic check, not a critic model. It is exact, free, and cannot itself
hallucinate.

### 3.4 Citation verification

The prompts require inline `[n]` markers, but a model can emit `[4]` when three passages were
supplied, and nothing downstream would notice. `workflow/verify.py` asserts every marker
resolves to a citation actually retrieved for that answer, strips the rest, and reports the
count. Across a fan-out, citations are **renumbered per agent** so two agents' `[1]` never
collide.

### 3.5 Provider chain

`build_chain` composes OpenAI then Anthropic, skipping any provider without a key and falling
back to `OfflineProvider` when none exists — so the app runs before it is configured. Each
call: budget guard → exact cache → providers in order. A provider failure is not a caller
error; the next one answers and `fallback_used` is recorded for the Internals page.

---

## 4. Key decisions and trade-offs

| Decision | Why | Cost |
|---|---|---|
| **model2vec instead of sentence-transformers** | No cp314 torch wheel exists on this platform (Intel macOS, Python 3.14). model2vec is numpy-only, free, offline-capable. | Static embeddings carry less contextual nuance than a transformer encoder. The BM25 half of hybrid retrieval is doing real work here, not decoration. |
| **NumpyIndex instead of FAISS** | At ~300 chunks an exact dot product is microseconds, and FAISS `IndexFlatIP` performs the identical brute-force scan. No cp314 wheel either. | Would need replacing at 10⁵+ chunks. `VectorIndex` is a Protocol, so that is a config change. |
| **Hand-rolled exact cache, not `set_llm_cache`** | LangChain's cache is transparent to the caller, so a hit is indistinguishable from a miss — and the Internals page must report *which* layer served the response. | A little more code for the same storage. |
| **Hand-authored corpus, not LLM-generated** | Free, deterministic, and every `source_url` is real. | Author time, and 77 documents rather than hundreds. |
| **yfinance, not Alpha Vantage** | Keyless. Alpha Vantage's free tier is 25 requests/day, which forces a quota tracker to work around. | Unofficial wrapper: it breaks on upstream changes (1.7 broke `fast_info`, so quotes derive from `Ticker.history()`) and throttles by IP. Mitigated by the TTL cache and a labelled mock at the end of the chain. |
| **Tool loop as a subgraph** | The main graph's `Send` fan-out targets a single node; a loop-back edge there would re-enter every fanned-out branch. | One more compiled graph to reason about. |
| **AsyncSqliteSaver, connection per call** | The graph is async; `SqliteSaver` raises on `aget_tuple`. State lives on disk, so a fresh connection still sees prior checkpoints. | Slight per-call overhead, avoided holding an event-loop-bound connection across Streamlit reruns. |

---

## 5. Testing strategy

47 tests. No network, no API spend — a session fixture replaces `socket.socket` so an
accidental connection fails loudly instead of billing.

| Layer | What is asserted |
|---|---|
| Architecture | The dependency rule, `core` purity, ≥2 implementations per Protocol, composition-root direction |
| Retrieval | RRF arithmetic, dimension-mismatch guard, the refusal gate, difficulty filtering, sparse independence, corpus integrity, embedding-cache persistence |
| Routing | 8 parametrized tier-1 cases, compound questions, comparison handling, all three tiers, fallback on tier-3 failure |
| Workflow | Reducer merge, concurrency timing, citation renumbering, crisis short-circuit, tool-loop termination and its cap, error containment |
| Cost | Zero-call cache hits, offline determinism, the budget kill switch, provider fallback, metered hits |

Every acceptance criterion maps to a named test in [`specs/traceability.md`](../specs/traceability.md).
Two structural bugs were found by the tests rather than by review — both recorded there.

---

## 6. Known limits and next steps

**Current limits.** Static embeddings are weaker than a transformer encoder. The corpus is 77
documents. yfinance is unofficial and throttles on shared egress IPs. Safety is regex plus
prompt posture, not a classifier — the code says so where it matters. There is no PII
redaction yet, so personas carry no real data by design.

**Phase 2** — cross-encoder reranking, HyDE and multi-query expansion, a reflection/critique
cycle, LLM-as-judge evals (faithfulness, answer relevancy, context precision) over a golden
set, semantic and prompt caching, the retrieval candidates table, `.github/instructions/*`
and `.github/agents/*`.

**Phase 3** — Monte Carlo goal projection with a P10/P50/P90 fan chart, portfolio theory
(Sharpe, Sortino, beta, correlation heatmap, VaR), risk-mismatch detection, news sentiment,
headline clustering, multimodal statement parsing, long-term per-persona memory, Presidio PII
redaction.

**Phase 4** — MCP server, voice, auth, Docker + Cloud Run, GitHub Actions CI with `ruff`.
