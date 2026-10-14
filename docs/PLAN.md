# Fintor — Multi-Agent AI Finance Tutor

> **Step 0 on approval:** persist this document into the repo as `docs/PLAN.md`, and seed `specs/000-overview.md` from it. The plan becomes a tracked project artifact, not a session scratchpad.

## Context

**The assignment.** IK-FDE capstone: multi-agent AI finance assistant — six specialist agents, RAG over a 50–100 article knowledge base, live market data, conversational UI. Rubric: Technical Implementation 40% (multi-agent 10, LangGraph 10, RAG 8, real-time data 7, MCP bonus 5), UX 25% (Streamlit 10, conversational flow 8, dataviz 7), Finance domain 20%, Code quality & docs 15%.

**The name.** **Fintor** — *fin* + *tutor*. States the product in one word: finance, taught. Sidesteps the advice-vs-education line the rubric grades. Mark: a bold `Fi` monogram in inline SVG.

**Priorities, in order.** (1) Maximum **variety of AI features, explainable in an interview.** (2) **Spec-driven development and AI governance**, demonstrable as artifacts. (3) **Hard cost discipline** — OpenAI credits are limited and binding. (4) **Modular design** with enumerated test cases. (5) Rubric coverage. (6) Surface polish.

**The benchmark.** `rramachandra33/clarityfi` — ~150 files over two weeks. FastAPI + React, Qdrant **and** FAISS, hand-written BM25 + RRF, semantic QA cache, Presidio PII redaction, MCP server (4 tools), **806 test functions**, 6 per-agent workflow docs, live deployment. Verified by reading its full tree: **no `SKILL.md`, no `.github/` customization, no `specs/`, no CI**, and no personalization beyond three static profile fields.

**Governance convention source.** `kvpatil/developer_setup_automation_copilot_customization` — the user's own repo, establishing the house style: GitHub Copilot customization under `.github/` (`copilot-instructions.md`, `instructions/*.instructions.md`, `agents/*.agent.md`, `skills/<name>/SKILL.md`). Two always-on conventions carry over verbatim: **docs updated with code, never deferred**, and **gitignore generated state at creation time**.

**Scope decision.** Nothing is cut. Full scope ~13–15 h, sequenced so **Phase 1 (335 min: 120 today + 215 tomorrow) ends with a complete, demoable, submittable app.** Later phases deepen what already works — never a half-wired feature on camera.

**Deployment.** GCP Cloud Run from a fresh account. Fully runnable locally throughout, so deployment can never block the demo.

---

## Modular design

Modularity is enforced by rules, not intentions — including a test that fails the build if the rules are broken.

### Dependency direction (strict, one-way)

```
web_app  →  workflow  →  agents  →  { rag, data }  →  core
```

`core` imports nothing internal. No module imports from a layer above it. Enforced by `test_no_upward_imports` (an architecture fitness function) — see the test matrix.

### Swap points — every external dependency behind a `typing.Protocol`

| Protocol (`core/ports.py`) | Implementations |
|---|---|
| `Embedder` | `LocalEmbedder` (MiniLM) · `OpenAIEmbedder` |
| `VectorIndex` | `FaissIndex` · (Qdrant in Phase 4) |
| `Retriever` | `HybridRetriever` · `DenseRetriever` · `SparseRetriever` |
| `ChatProvider` | `OpenAIProvider` · `AnthropicProvider` · `OfflineProvider` |
| `CacheBackend` | `SqliteCache` · `MemoryCache` · `NullCache` |
| `MarketDataProvider` | `YFinanceProvider` · `MockProvider` · (AlphaVantage, Phase 2) |
| `NewsProvider` | `YFinanceNews` · `RssNews` · `MockNews` |

Every protocol has **at least two implementations**, which is what makes the seams real rather than decorative — and what makes the tests fast, since fakes substitute cleanly.

### Other structural rules

- **Composition root.** All wiring happens in `core/container.py`, driven by `config.yaml`. No module constructs its own dependencies; nothing reads env vars outside `core/config.py`.
- **Contracts.** Pydantic models in `core/contracts.py` are the only data shapes crossing a layer boundary (`Query`, `RouteDecision`, `RetrievedChunk`, `Citation`, `AgentResult`, `Persona`, `CostRecord`).
- **Uniform agents.** Each subclasses `BaseAgent` and implements only `_execute`. Adding a seventh agent touches one new file plus one registry line — nothing else.
- **No business logic in Streamlit pages.** Pages render and call into `workflow`; any logic in a page is a bug.
- **Pure where possible.** Quant and retrieval-fusion functions take data and return data — no I/O, no globals — which is why they're trivially testable.

---

## Architecture

```
fintor/
├── .github/
│   ├── copilot-instructions.md
│   ├── instructions/*.instructions.md      # Phase 2
│   ├── agents/*.agent.md                   # Phase 2
│   └── skills/<name>/SKILL.md              # 5 skills, Block A
├── docs/
│   ├── PLAN.md                             # this document, persisted
│   ├── design.md                           # + 8 Mermaid diagrams
│   └── diagrams/                           # committed PNG fallbacks
├── specs/                                  # numbered specs + traceability
├── src/
│   ├── agents/        # 6 specialists + base
│   ├── core/          # ports, contracts, container, config, llm, cache, cost, quant, safety
│   ├── data/          # yfinance + news clients, KB builder, personas
│   ├── rag/           # hybrid retriever, reranker, query transforms, index
│   ├── web_app/       # Streamlit app + pages
│   ├── mcp_server/    # Phase 4
│   ├── utils/
│   └── workflow/      # graph, router, tools, memory, verify
├── evals/ · tests/ · deploy/
├── config.yaml · requirements.txt · README.md
```

**Stack.** Python 3.12 · Streamlit · LangGraph · LangChain · FAISS + `rank_bm25` · `sentence-transformers` · **OpenAI + Anthropic** · `yfinance` + `feedparser` (keyless) · Plotly · SQLite · Docker · Cloud Run.

**UI add-ons.** `streamlit-flow-component` · `streamlit-mermaid` · `st-annotated-text` · `streamlit-extras`. Rejected: `streamlit-elements` (loosely maintained), `streamlit-aggrid` (heavy, version-pinning pain), `streamlit-option-menu` (native `st.navigation` does grouped sections with one fewer dependency).

**Graph topology** — cyclic, unlike the benchmark's strict DAG:

```
START → guard → router ──Send(fan-out)──> agent ⇄ tools
                                            │
                                            ▼
                                   critic ──(revise ≤1)──┐
                                            │            │
                                            └────────────┘
                                            ▼
                                 synthesize → verify → END
```

---

## Architecture diagrams

Eight Mermaid diagrams, rendered on the **Architecture** page in-app and embedded in `docs/design.md`. Committed PNG fallbacks in `docs/diagrams/` in case the Mermaid component misbehaves on Cloud Run.

| # | Diagram | Type | Source |
|---|---|---|---|
| 1 | **LangGraph workflow** | flowchart | **Auto-generated** via `graph.get_graph().draw_mermaid()` on the *compiled* graph — cannot drift from the code |
| 2 | **System architecture** | flowchart | Layers, components, external boundaries |
| 3 | **Module dependency** | flowchart | The one-way rule above, with the fitness-function test annotated |
| 4 | **Request sequence** | sequenceDiagram | User → guard → router → agents → tools → synthesize → verify → UI |
| 5 | **RAG pipeline** | flowchart | Query → embed → dense ∥ sparse → RRF → (rerank) → gate → prompt → cited answer |
| 6 | **Caching & cost flow** | flowchart | The seven layers as a decision path, showing where each short-circuits |
| 7 | **Persona conditioning** | flowchart | Persona → prompt injection + difficulty filter + `thread_id` selection |
| 8 | **Deployment topology** | flowchart | Cloud Run + Secret Manager + GCS volume + baked index |

Diagram 1 is the one worth calling out in an interview: generating the architecture diagram *from the compiled graph object* means the documentation is structurally incapable of going stale.

---

## Cost discipline

Limited OpenAI credits are a hard constraint. Block B alone is ~215 minutes of Streamlit iteration — without these controls, every rerun bills.

### Seven caching layers

| # | Layer | Mechanism | Phase |
|---|---|---|---|
| 1 | **LLM exact response** | LangChain `SQLiteCache` via `set_llm_cache` — on disk, survives restarts | 1 |
| 2 | **Semantic answer** | Question embedding, cosine ≥0.90, guarded against differing numbers (401k≠403b), negation flips, comparatives | 2 |
| 3 | **Provider prompt cache** | **OpenAI: automatic** ≥1024 tokens. **Anthropic: explicit** `cache_control: ephemeral` | 2 |
| 4 | **Embedding cache** | **SQLite on disk**, keyed `sha256(model‖text)` + in-batch dedupe. KB embedded once, *ever* | 1 |
| 5 | **Market data** | TTL (quotes 30 min, history 6 h) + stale-while-error fallback with honest labels. Doubles as yfinance throttle protection | 1 |
| 6 | **Retrieval** | `query → candidate ids`, invalidated on KB version bump | 2 |
| 7 | **Streamlit resources** | `@st.cache_resource` for embedder / cross-encoder / index singletons; `@st.cache_data` for frames | 1 |

**Gotcha:** Anthropic prompt caching needs a ≥1024-token cacheable prefix (2048 for Haiku) — below that it silently never engages.

### Six non-cache controls

1. **`FINTOR_OFFLINE=1` mock mode** — deterministic canned responses via `OfflineProvider`. All of Block B's UI work costs **zero**. The single largest saver.
2. **Committed index** — FAISS + BM25 + `records.json` in the repo, so graders and Cloud Run never re-embed.
3. **Model tiering** — `gpt-4o-mini` default; strong model only on explicit escalation. Router tiers 1–2 are free.
4. **Session budget guard** — hard token/USD ceiling with a kill switch; `max_tokens` caps; context truncated before the prompt.
5. **Live cost bar** in AI Internals — tokens, USD, budget remaining, per-persona ledger.
6. **Recorded fixtures** — captured responses so `pytest` never spends a cent, enforced by the cost-discipline skill and a network-blocking fixture.

### Market & news data — free, no API keys

**Quotes/history: `yfinance`** — free, keyless, no signup quota. Chosen over Alpha Vantage deliberately: its free tier is **25 requests/day, 5/min**, which is why the benchmark needed a `QuotaGuard` plus a DB-persisted usage tracker. The brief accepts either, so yfinance satisfies the rubric at zero cost.

**News: `yfinance` `Ticker.news` + RSS via `feedparser`** — also keyless. The benchmark used SerpAPI at 100 calls/*month*.

**Three-tier chain:** fresh cache → live provider → last-good stale cache (labeled) → deterministic mock (labeled "sample data, not real"). This chain *is* the rubric's "Real-time Data Integration (7%): robust API integration with proper error handling."

**Two yfinance caveats designed around:** it's an unofficial Yahoo wrapper that breaks on response-shape changes (**pin the version**; mock fallback means a break never kills a demo); and **Cloud Run is throttled harder** since requests share a Google egress IP (mitigated by the TTL cache plus committed snapshot data for the recording).

**Optional (Phase 2):** Alpha Vantage as a *configured fallback only*, for graders grepping the brief's name. `FRED` in Phase 3 for Sharpe's risk-free rate.

**Net: no API keys except the LLM ones** — and with `FINTOR_OFFLINE=1`, not even those.

### Embeddings — config switch, local by default

`config.yaml → rag.embeddings: local | openai`

- **`local`** (default): `all-MiniLM-L6-v2`, 384-d, ~90 MB, $0 forever, no key. Quality gap recovered by BM25 plus the Phase 2 cross-encoder.
- **`openai`**: `text-embedding-3-small`, 1536-d, better recall, ~$0.006 one-time for the KB.

The index records its model and dimension; a mismatch raises a hard "rebuild required" rather than silently mixing vector spaces.

---

## Spec-driven development

The demonstrable artifact is **git history plus a traceability matrix**, not a README claim.

**Process.** Write the spec → commit it → implement → commit referencing the spec ID (`feat(router): SPEC-002 tiers 1–2`). The directory is not yet a git repo, so `git init` is minute 0.

**Spec format** (`specs/NNN-name.md`): Intent · Contract (references `core/contracts.py`) · **numbered, executable acceptance criteria** · Edge cases · Non-goals · Status.

**Phase 1 specs:** `000-overview`, `001-retrieval`, `002-routing`, `003-orchestration`, `004-caching-and-cost`, `005-personas`.

**Traceability** (`specs/traceability.md`): generated table of spec ID → acceptance criterion → test name → status.

---

## Test cases

Phase 1 ships **11 tests**, every one fast, deterministic, offline, and tied to a spec acceptance criterion. A session-scoped fixture blocks `socket` so a test that tries to reach the network fails loudly rather than billing.

| Test | Spec | Asserts |
|---|---|---|
| `test_rrf_fusion_orders_by_reciprocal_rank` | 001 | Known dense + sparse rankings fuse to the expected order; verifies the `k=60` math |
| `test_index_rejects_embedding_dimension_mismatch` | 001 | A 384-d index loaded with a 1536-d embedder raises `RebuildRequired`, never mixes spaces |
| `test_retrieval_gate_refuses_below_threshold` | 001 | All candidates under threshold → refusal, and **no LLM call is made** |
| `test_router_tier1_regex_confident_cases` | 002 | Parametrized labeled set: correct intents, tier 1 resolves without escalating |
| `test_router_escalates_to_tier3_when_ambiguous` | 002 | Ambiguous input reaches the LLM tier (fake model) and never raises |
| `test_graph_fanout_merges_parallel_agent_results` | 003 | Compound question fans out to 2 agents; the `operator.add` reducer merges both; citations renumber without collision |
| `test_tool_node_loops_back_and_terminates` | 003 | Tool call → `ToolNode` → agent → terminates; iteration cap prevents an infinite loop |
| `test_exact_cache_returns_without_provider_call` | 004 | Second identical call invokes the fake provider **zero** times; tier reported as `exact` |
| `test_budget_guard_blocks_when_ceiling_exceeded` | 004 | A $0.00 ceiling raises `BudgetExceeded` with an actionable message; no spend occurs |
| `test_offline_mode_makes_no_network_calls` | 004 | Full graph run succeeds with sockets blocked |
| `test_no_upward_imports` | 000 | **Architecture fitness function** — walks the AST of every module and fails if any layer imports from a layer above it |

**Fakes** (`tests/conftest.py`): `FakeChatProvider` (counts invocations, returns scripted text), `FakeEmbedder` (deterministic vectors), `FakeMarketProvider`, plus recorded JSON fixtures. No test touches a paid API — enforced by the `llm-cost-discipline` skill.

**Phase 2 expands to ~25**, adding: cross-encoder rerank ordering · HyDE query generation shape · citation verification strips unresolvable `[n]` markers · semantic-cache guards (numbers, negation, comparatives) · eval-metric computation on fixed inputs · reflection triggers only below the groundedness threshold · per-persona thread isolation · provider fallback engages on primary failure.

---

## AI governance — `.github/` Copilot customization

Follows the house style exactly: frontmatter shape, "Your goal is to help me…" / "You are a specialist in…" openings, `## Constraints` / `## Approach` sections, relative links instead of duplication, comments explaining *why* not *what*.

These are not decorative. Because Claude writes the implementation, these files actively steer the code that follows — the argument for governance-first sequencing.

**`.github/skills/<name>/SKILL.md`** — five skills (Block A):

| Skill | Encodes |
|---|---|
| `finance-compliance` | Education-not-advice boundary; mandatory disclaimer; no buy/sell recommendations; no personal tax computation; no price predictions; refusal-and-redirect phrasing |
| `ai-grounding` | Every figure traces to computed facts or retrieved context; inline `[n]` citations required and verified; refuse rather than generate below threshold |
| `llm-cost-discipline` | Never call a paid API from a test; offline mode for UI work; check the cache before adding a call; local embeddings default; model tiering |
| `prompt-safety` | User text and retrieved headlines are data, never instructions; PII fail-closed; injection posture; trace redaction |
| `spec-driven-development` | No implementation without a spec, numbered acceptance criteria, and a test; spec ID in the commit message |

**`.github/copilot-instructions.md`** (Block A) — Fintor's `## Stack & layout` and `## Always-on conventions`, carrying over docs-with-code and gitignore-at-creation, plus the education-not-advice boundary and the dependency-direction rule as repo-wide constraints.

**`.github/instructions/*`** and **`.github/agents/*`** (Phase 2) — `python-backend`, `streamlit-ui`, `langgraph-workflow`; `rag-retrieval` and `agent-orchestration` specialists.

---

## Technique catalogue

### Phase 1 — the 335-minute submittable milestone

| # | Technique | File | Interview point |
|---|---|---|---|
| 1 | **Multi-agent fan-out** — `StateGraph` + `Send()`, `Annotated[list, operator.add]` reducer | `workflow/graph.py` | Why concurrent state writes need a reducer |
| 2 | **Tool calling / ReAct** — `@tool` + `bind_tools` + `ToolNode`, loop-back edge | `workflow/tools.py` | Benchmark's biggest gap: zero tool calling anywhere |
| 3 | **Durable state** — `SqliteSaver` checkpointer + `thread_id` | `workflow/graph.py` | Checkpointers vs. app-level history |
| 4 | **Three-tier router** — regex → embedding k-NN vs intent centroids → LLM `with_structured_output` | `workflow/router.py` | Escalating cost per tier; tiers 1–2 are free |
| 5 | **Hybrid retrieval + RRF** — FAISS dense + `rank_bm25`, fused k=60 | `rag/retriever.py` | Why rank fusion beats score normalization |
| 6 | **Provider fallback + cost tiers** — OpenAI → Claude via `.with_fallbacks()`, token + USD meter | `core/llm.py` | Graceful degradation across providers |
| 7 | **Cache layers 1, 4, 5, 7 + offline mode + budget guard** | `core/cache.py`, `core/cost.py` | Where each tier pays off |
| 8 | **Streaming** — `astream_events(version="v2")` → `st.write_stream`, plus `st.status` live agent-handoff trace | `web_app/app.py` | Perceived vs actual latency |
| 9 | **Six agents** — distinct prompts, structured output, per-agent model tier + retrieval slice | `agents/*.py` | Specialization vs one mega-prompt |
| 10 | **AI Internals page** with the live graph visualization | `web_app/pages/internals.py` | The demo centerpiece |
| 11 | **Persona personalization** — prompt conditioning, difficulty-filtered retrieval, per-persona threads | `data/personas.py` | Benchmark has no personalization beyond three static fields |

### Phase 2 — retrieval & evaluation depth (~3 h)

Cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`, local, free) · HyDE + multi-query expansion, toggleable live · reflection/critic cycle · citation verification · **LLM-as-judge evals** (faithfulness, answer relevancy, context precision over a 20-question golden set + router accuracy) · feedback loop wiring `st.feedback` into the eval dataset · semantic cache (layer 2) · prompt caching (layer 3) · retrieval cache (layer 6) · `annotated-text` citation highlighting · retrieval candidates table · `.github/instructions/*` + `.github/agents/*` · tests 11 → 25.

### Phase 3 — quant, applied ML, multimodal (~3 h)

Monte Carlo (10k paths, P10/P50/P90 fan chart, probability of success) · portfolio theory (Sharpe, Sortino, beta vs SPY, correlation heatmap, VaR, HHI) · risk-mismatch detection · news sentiment via structured output · headline clustering/dedup on embeddings · multimodal statement/screenshot → holdings · long-term vector memory learning per persona across sessions · Presidio PII redaction + LLM moderation.

*All fill verified gaps: the benchmark has no Monte Carlo, no portfolio theory at all (its goal projection defaults to 0% growth), no sentiment, no clustering, no OCR, and regex-only safety by its own admission.*

### Phase 4 — platform & ship (~3 h)

MCP server (rubric's 5% bonus) · voice (Whisper STT + TTS) · minimal auth · Docker + Cloud Run · **GitHub Actions CI + `ruff`** (benchmark has none).

---

## UI layer

**Theme & type** — `.streamlit/config.toml` tokens plus injected CSS: serif display face, `font-variant-numeric: tabular-nums` on every figure (digits align and stop jittering as values update — the biggest "serious financial UI" tell), tighter radii, hairline rules, matched dark/light.

**Native features doing real work:** `st.write_stream` · `st.status` + nested writes (live agent-handoff trace) · `st.column_config` · `st.feedback("thumbs")` · `st.fragment` (Internals refreshes without re-running the graph) · `st.navigation` + `st.Page` (grouped sections, real URLs, Material icons).

### Navigation — two groups

```
Workspace          About Fintor
├── Chat           ├── Architecture
├── Portfolio      ├── Design Document
├── Market         ├── Governance
├── Goals          └── Recording
└── AI Internals
```

Chat and AI Internals are fully built in Phase 1. Portfolio, Market, and Goals ship functional but plain (dataframe + one Plotly chart each); richer dataviz arrives in Phase 3.

**About Fintor:** **Architecture** (the 8 diagrams, #1 auto-generated from the compiled graph) · **Design Document** (renders `docs/design.md` with a download button) · **Governance** (renders the 5 skills, `copilot-instructions.md`, and the traceability matrix) · **Recording** (`st.video`).

---

## The AI Internals page

- **Graph trace** — nodes visited, per-node timing, agents fanned out, tool calls made
- **Router decision** — which tier fired and why
- **Active persona** — which profile conditioned the prompt, and the difficulty filter applied
- **Cache tier** — which of the seven layers hit, with similarity and matched question
- **Cost** — provider used (and whether fallback triggered), tokens, USD, budget remaining, per-persona ledger
- **Retrieval table** — dense rank, BM25 rank, RRF score, cross-encoder delta (Phase 2)
- **Guardrails** — citations verified vs stripped (Phase 2)
- **Eval scores** — faithfulness / relevancy / context precision (Phase 2)

ClarityFI hides all of this. Exposing it is the highest-leverage differentiator available.

---

## Personas — six user journeys

Serves the brief's own business case: *"Personalized Learning Paths… adapts to each user's knowledge level, goals, and risk tolerance."* No login gate — instant switching, strictly better for a demo than ClarityFI's auth wall.

| Persona | Profile | Journey showcases |
|---|---|---|
| **Maya, 24** — First Paycheck | Beginner · $3k cash · no holdings | Beginner-level retrieval, jargon-free Q&A, emergency-fund goal |
| **Dev, 31** — Concentrated | Intermediate · 70% employer stock | Concentration risk, diversification, capital-gains education |
| **Priya, 38** — Index Investor | Intermediate · VTI/VXUS/BND · house in 5 yrs | Goal planning + on-track check |
| **Walter, 61** — Near Retirement | Advanced · bond-heavy | Sequence-of-returns risk, withdrawal and RMD concepts |
| **Aisha, 29** — Crypto-Heavy | Intermediate · 40% BTC/ETH | Volatility, correlation, risk-tolerance framing |
| **Sam, 45** — Tax-Focused | Advanced · 401k/HSA/Roth | Tax-advantaged accounts, asset location |

Each carries profile fields, holdings, goals, **and 3–4 scripted journey prompts** — each hitting a different agent and technique, doubling as the demo script.

**How personas touch the AI layer:** profile injected into every agent's system prompt · **difficulty-filtered retrieval** (beginners get `difficulty: beginner` chunks only — a metadata-filter demo over one corpus, nearly free since the KB schema already carries it) · **per-persona `thread_id`** so the checkpointer keeps isolated state · per-persona cost ledger.

**The demo beat:** ask *"should I buy more NVDA?"* as Dev (70% concentrated), then as Walter (near retirement). Same agents, same corpus, materially different answers. Thirty seconds, personalization proven.

All personas synthetic and labeled **"a teaching example, not a real account."**

---

## Knowledge base

`src/data/build_kb.py` — seeded term list (SEC Investor.gov, IRS, Bogleheads topics) expanded by one scripted LLM pass into **60 documents**: `{term, aliases, category, difficulty, definition, example, related_terms, source_name, source_url}`. Chunk 1000 / overlap 150; `source_name` + `source_url` carried into citation metadata. **Built once, index committed.**

---

## Timeline

**Block A — today, 120 min. Governance first, then backend. Hard gate: a real query answers end-to-end by minute 120.**

| Min | Work |
|---|---|
| 0–28 | `git init`, scaffold, `.gitignore`, `config.yaml`, `requirements.txt`; **persist `docs/PLAN.md`**; `copilot-instructions.md` + 5 × SKILL.md; `specs/000-overview.md`; `core/ports.py` + `contracts.py` skeletons |
| 28–40 | Provider layer (OpenAI→Claude fallback, cheap/strong tiers), cost meter + budget guard, **offline mode** |
| 40–50 | Cache foundation — disk embedding cache, `SQLiteCache` |
| 50–68 | `build_kb.py` → 60 docs → embeddings (local default) → FAISS + BM25 + RRF; **commit index** [SPEC-001] |
| 68–88 | Six agents + three-tier router [SPEC-002] |
| 88–110 | LangGraph: fan-out, tools/ReAct, checkpointer [SPEC-003] |
| 110–120 | `yfinance` quote/history tools + keyless news; **first end-to-end query via CLI, offline and live** |

Governance goes first deliberately — the skills constrain every file written after them.

**Block B — tomorrow, 215 min. UI, tests, docs, ship.**

| Min | Work |
|---|---|
| 0–10 | `config.toml` + CSS tokens + `st.cache_resource` wiring |
| 10–22 | `st.navigation` two-group nav + 9-page shell; Portfolio/Market/Goals plain |
| 22–50 | **Persona backend** — model + 6 seeds, prompt conditioning, difficulty filter, per-persona `thread_id` [SPEC-005] |
| 50–65 | **Persona UI** — sidebar selector, profile card, journey prompt chips |
| 65–85 | Chat page: `st.write_stream` + `st.status` live trace + `st.feedback` |
| 85–109 | **`streamlit-flow` LangGraph visualization** |
| 109–124 | AI Internals: cost/budget bar, cache tier, router tier, graph trace, active persona |
| 124–139 | About Fintor: Architecture, Design Document, Governance, Recording |
| 139–160 | **11 tests + fakes/fixtures + `specs/traceability.md`** [SPEC-004] |
| 160–188 | **`docs/design.md` + the 8 Mermaid diagrams** + PNG fallbacks |
| 188–197 | README polish |
| 197–215 | Demo script (one beat per persona, mapped to rubric items) + **record video** |

Per the house convention the README is written **with** the code throughout; 188–197 is polish, not first draft.

**If Block B slips**, defer in this order: data-page Plotly charts → diagrams 6–8 → two personas (ship four). Protected: the flow-graph visualization, the persona selector, diagrams 1–5, the 11 tests (they carry the spec-driven claim), the README, and the demo video.

---

## GCP deployment, from a fresh account (Phase 4)

Free tier plus $300/90-day credits covers this.

1. Sign up at `cloud.google.com`, install `gcloud`, `gcloud init`.
2. `gcloud projects create fintor-<suffix>`; link billing.
3. Enable `run`, `cloudbuild`, `artifactregistry`, `secretmanager`.
4. `gcloud secrets create OPENAI_API_KEY --data-file=-` (same for `ANTHROPIC_API_KEY`).
5. `gcloud run deploy fintor --source . --region us-central1 --allow-unauthenticated --session-affinity --cpu 2 --memory 2Gi --min-instances 1 --set-secrets=...`

**Streamlit-on-Cloud-Run specifics, each a real failure if missed:**

- Bind `--server.port=$PORT --server.address=0.0.0.0 --server.headless=true`.
- **`--session-affinity` is required** — Streamlit holds per-session state over a WebSocket; without sticky routing, sessions break as instances scale.
- `--min-instances 1` avoids a demo-time cold start; `--memory 2Gi` because torch + local models are heavy.
- **Cloud Run is stateless.** The FAISS index is baked into the image (static, already committed). The SQLite checkpointer needs a GCS volume mount or accepts ephemeral state. *This stateless-compute-vs-durable-state tension is a good interview topic.*

---

## Verification

1. **Offline first:** `FINTOR_OFFLINE=1 streamlit run src/web_app/app.py` — every page renders and the graph executes with zero API spend. The default development mode.
2. **End-to-end live:** "What is an HSA?" (RAG + citations) · "How is AAPL doing?" (tool calling + live data) · "Can I retire at 55 on $4k/month?" (structured extraction) · "How are capital gains taxed and how is SPY doing?" (multi-agent fan-out).
3. **Personas:** ask *"should I buy more NVDA?"* as **Dev** then **Walter** — materially different answers from the same agents. Maya's retrieval returns only beginner chunks; Walter's draws the full corpus. Switch personas and back; each thread's history is preserved and isolated.
4. **Caching:** ask verbatim twice → exact hit, zero tokens, tier shown in Internals. Restart → embedding cache preserved, no re-embedding.
5. **Budget guard:** set a $0.01 ceiling; the kill switch fires with a clear message.
6. **Provider fallback:** invalidate the OpenAI key; the chain degrades to Claude, visible in Internals.
7. **Embeddings switch:** flip `rag.embeddings` to `openai`; the dimension guard demands a rebuild rather than mixing spaces.
8. **Durable state:** restart, resume the same `thread_id`, history survives.
9. **Tests & specs:** `pytest -q` → 11 green; every Phase 1 acceptance criterion maps to a named test in `specs/traceability.md`; `test_no_upward_imports` passes.
10. **Governance:** the Governance page renders all five skills plus `copilot-instructions.md`; `git log` shows spec commits preceding implementations; frontmatter matches the reference repo's house style.
11. **Diagrams:** all 8 render on the Architecture page; diagram 1 regenerates from the compiled graph (change a node, confirm the diagram changes).
12. **Deploy (Phase 4):** Cloud Run URL serves the app; reload mid-session confirms session affinity holds.

---

## Not in scope

Only what the brief doesn't ask for: real brokerage/Plaid linkage, budgeting and net-worth tracking, tax computation (deliberately — education only), mobile apps, i18n.
