# Fintor

**Finance, taught.** A multi-agent AI finance tutor: six specialist agents answer money
questions in plain English, grounded in a cited knowledge base, enriched with keyless live
market data, and conditioned on a selectable persona. It explains; it does not give personal
financial, investment, legal or tax advice, and every answer says so.

```
Workspace                    About Fintor
├── Chat                     ├── Architecture      (8 diagrams, #1 generated from the graph)
├── Portfolio                ├── Design Document
├── Market                   ├── Governance        (5 SKILL.md + traceability)
├── Goals                    └── Recording
└── AI Internals  ← the machinery, made visible
```

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Runs with no API keys at all: canned responses, zero network, zero spend.
FINTOR_OFFLINE=1 .venv/bin/streamlit run src/web_app/app.py

# Live: add OPENAI_API_KEY to .env (cp .env.example .env), then
.venv/bin/streamlit run src/web_app/app.py
```

The retrieval index is **committed**, so there is nothing to build before first run. Market
and news data need **no API keys** — yfinance and RSS are both keyless.

```bash
.venv/bin/python -m pytest -q          # 47 tests, no network, no spend
.venv/bin/python -m src.rag.build      # rebuild the index (only after corpus changes)
```

## What is in here

| Capability | Where |
|---|---|
| **Multi-agent fan-out** — `Send()` + `operator.add` reducer, agents run concurrently | `src/workflow/graph.py` |
| **Tool calling / ReAct** — `@tool` + `bind_tools` + `ToolNode` with a capped loop-back | `src/workflow/tools.py` |
| **Durable threads** — `AsyncSqliteSaver`, one thread per persona | `src/workflow/graph.py` |
| **Three-tier router** — regex → embedding k-NN vs intent centroids → LLM structured output | `src/workflow/router.py` |
| **Hybrid retrieval** — dense + BM25 fused by Reciprocal Rank Fusion (k=60) | `src/rag/retriever.py` |
| **Provider fallback** — OpenAI → Anthropic → offline, with per-call cost metering | `src/core/llm.py` |
| **Seven cache layers** + session budget kill switch | `src/core/cache.py`, `src/core/cost.py` |
| **Numeric grounding guard** — invented figures discard the whole narration | `src/agents/narration.py` |
| **Citation verification** — every `[n]` must resolve to a retrieved passage | `src/workflow/verify.py` |
| **Persona personalization** — prompt conditioning, difficulty-filtered retrieval, isolated threads | `src/data/personas.py` |
| **Six agents** | `src/agents/` |

Full rationale and all eight architecture diagrams: **[docs/design.md](docs/design.md)**.
The implementation plan: **[docs/PLAN.md](docs/PLAN.md)**.

## Personas

Switching persona changes the answer, not just the portfolio. Ask *"Should I buy more NVDA?"*
as **Dev** (70% in employer stock) and then as **Walter** (four years from retirement) — same
agents, same corpus, materially different answers.

| Persona | Profile | Computed risk / diversification |
|---|---|---|
| **Maya**, 24 | Beginner · $3k cash, no holdings | 10 / 18 |
| **Dev**, 31 | Intermediate · 70% employer stock | 78 / 35 |
| **Priya**, 38 | Intermediate · VTI/VXUS/BND, house in 5y | 52 / 80 |
| **Walter**, 61 | Advanced · bond-heavy, near retirement | 38 / 73 |
| **Aisha**, 29 | Intermediate · 40% crypto | 90 / 52 |
| **Sam**, 45 | Advanced · tax-focused | 53 / 86 |

All personas are synthetic teaching examples, never real accounts.

## Cost discipline

OpenAI credits were a binding constraint on this build, so cost is a design feature rather
than an afterthought.

- **`FINTOR_OFFLINE=1`** runs the full workflow — routing, retrieval, fan-out, metering — with
  the language model replaced by deterministic canned responses. Zero network, zero spend.
- **Local embeddings by default** (model2vec, 256-d, no torch). `rag.embeddings: openai`
  switches to hosted; the index refuses to load against a mismatched embedder.
- **Seven cache layers**, from exact LLM responses on disk to Streamlit resource singletons.
  Cache hits are still metered with `usd = 0` — a saving nobody can measure is a saving nobody
  believes.
- **A hard session budget** (`cost.session_budget_usd`) that raises before spending, not after.
- **Tests never pay.** A session fixture blocks `socket`, so an accidental call fails loudly.

The **AI Internals** page shows all of it live: routing tier, retrieval ranks, cache tier,
tokens, USD, budget remaining, per-persona spend.

## Spec-driven development

Every feature has a numbered spec in [`specs/`](specs/) with executable acceptance criteria,
committed **before** its implementation. `git log` shows the ordering; the mapping from
criterion to test lives in [`specs/traceability.md`](specs/traceability.md).

Two structural bugs were caught by those tests rather than by review:

1. `test_no_upward_imports` found the composition root sitting in `core` — the bottom layer —
   while importing from every layer above it.
2. A workflow criterion found that the graph's agent node contained only `TimeoutError`, so an
   agent failing outside `BaseAgent`'s contract took down every fanned-out branch.

## AI governance

Guardrails live as repository artifacts in GitHub Copilot customization format, and were
committed **first** — they constrain the code written after them. Rendered in-app on the
**Governance** page.

| Skill | Encodes |
|---|---|
| [`finance-compliance`](.github/skills/finance-compliance/SKILL.md) | The education/advice boundary, disclaimers, refusal-and-redirect phrasing |
| [`ai-grounding`](.github/skills/ai-grounding/SKILL.md) | Figures trace to computed facts; citations verified; refuse below threshold |
| [`llm-cost-discipline`](.github/skills/llm-cost-discipline/SKILL.md) | Cache before calling; never pay in a test; local embeddings default |
| [`prompt-safety`](.github/skills/prompt-safety/SKILL.md) | User and third-party text are data, never instructions; PII fail-closed |
| [`spec-driven-development`](.github/skills/spec-driven-development/SKILL.md) | No code without a spec, criteria, and a test |

Plus [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for repo-wide
conventions, including the one-way dependency rule.

## Architecture at a glance

```
web_app  →  workflow  →  agents  →  { rag, data }  →  core
```

Strictly one-way, enforced by a build-time test. Every external dependency sits behind a
`typing.Protocol` in `src/core/ports.py` with at least two implementations, which is what
makes the seams real and the tests fast.

```
fintor/
├── .github/{copilot-instructions.md, skills/}   AI governance
├── specs/                                        numbered specs + traceability
├── docs/{design.md, PLAN.md}
├── src/
│   ├── container.py      composition root (imports everything; only entry points import it)
│   ├── core/             ports · contracts · llm · cache · cost · quant · safety · config
│   ├── rag/              embeddings · index · retriever · categories · build
│   ├── data/             market · news · personas · kb/ (corpus + committed index)
│   ├── agents/           6 specialists · base · narration · registry
│   ├── workflow/         graph · router · tools · verify
│   └── web_app/          app.py · gate · chrome · views/ · theme · brand · assets/
└── tests/                47 tests
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `IndexMismatch: index was built with … ` | The embedding model changed. `python -m src.rag.build --reset`. |
| `BudgetExceeded` | Session budget spent. Raise `cost.session_budget_usd`, or use `FINTOR_OFFLINE=1`. |
| Market data shows `SAMPLE DATA` | Yahoo throttled or changed shape. The chain fell through to the labelled mock; wait, or rely on the TTL cache. |
| Answers say `[offline mode]` | `FINTOR_OFFLINE=1` is set, or no `OPENAI_API_KEY` is configured. |
| Mermaid diagrams render as code blocks | `streamlit-mermaid` failed to load; the raw diagram source is shown as a fallback. |

## Known limits

Static embeddings are weaker than a transformer encoder. The corpus is 77 documents. yfinance
is an unofficial wrapper. Safety is regex plus prompt posture, not a classifier. No PII
redaction yet — which is why personas carry no real data. Phase 2–4 work is listed at the end
of [docs/design.md](docs/design.md).

---

*Educational only. Not financial, investment, legal or tax advice.*
