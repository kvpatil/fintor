"""About Fintor: Architecture, Design Document, Governance, Recording."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.core.config import ROOT
from src.web_app.state import get_deps


def _mermaid(code: str) -> None:
    """Render a Mermaid diagram at the size it actually is.

    No `height` argument, deliberately. Every call site used to pass a
    hand-guessed pixel string and every one of them was wrong - measured in the
    browser, two diagrams were clipped (the caching one lost 453px of 1027) and
    four wasted 142-354px of dead space. `st_mermaid` already defaults to
    `height="auto"`, and its frontend calls `setFrameHeight(bbox.height + 16)`
    after rendering, so the component sizes its own frame from the real SVG.
    Passing a number was overriding a mechanism that already worked.

    Controls off: these are static figures, and the pan/zoom/RESET overlay sat
    on top of the `__end__` node in the generated graph.
    """
    try:
        import streamlit_mermaid as stmd

        stmd.st_mermaid(code, pan=False, zoom=False, show_controls=False)
    except Exception:  # noqa: BLE001
        st.code(code, language="mermaid")


SYSTEM_DIAGRAM = """flowchart TB
  U["Streamlit UI<br/>pages + persona selector"] --> WF["workflow<br/>graph · router · tools · verify"]
  WF --> AG["agents<br/>6 specialists + narration"]
  AG --> RAG["rag<br/>hybrid retriever · index · embeddings"]
  AG --> DATA["data<br/>yfinance · RSS · personas · corpus"]
  RAG --> CORE["core<br/>ports · contracts · container · llm · cache · cost · quant · safety"]
  DATA --> CORE
  CORE --> EXT["OpenAI · Yahoo Finance · RSS"]
"""

MODULE_DIAGRAM = """flowchart LR
  web_app --> workflow --> agents --> rag --> core
  agents --> data --> core
  core -.->|imports nothing internal| core
"""

RAG_DIAGRAM = """flowchart LR
  Q[Question] --> E[Embed]
  Q --> B[BM25 tokenize]
  E --> D[Dense top-20]
  B --> S[Sparse top-20]
  D --> F["RRF fuse<br/>k=60"]
  S --> F
  F --> C[Recompute cosine]
  C --> DF["Difficulty + category filter<br/>(persona)"]
  DF --> G{"score >= 0.25?"}
  G -->|no| R["Refuse<br/>no LLM call"]
  G -->|yes| P[Numbered passages to LLM]
  P --> V["Verify [n] markers"]
"""

CACHE_DIAGRAM = """flowchart TB
  A[Request] --> BG{"Budget left?"}
  BG -->|no| K["BudgetExceeded<br/>kill switch"]
  BG -->|yes| L1{"Layer 1<br/>exact response?"}
  L1 -->|hit| Z["Return, 0 tokens"]
  L1 -->|miss| L4{"Layer 4<br/>embedding cached?"}
  L4 -->|hit| M[Skip embedding call]
  L4 -->|miss| N[Embed once, store]
  M --> P[Provider call]
  N --> P
  P --> R[Record CostRecord]
"""

PERSONA_DIAGRAM = """flowchart LR
  PS[Persona selected] --> PP[Prompt preamble<br/>experience level + risk]
  PS --> DC[Difficulty ceiling<br/>corpus filter]
  PS --> TH["thread_id<br/>isolated checkpoint"]
  PP --> ANS[Answer]
  DC --> ANS
  TH --> ANS
"""

DEPLOY_DIAGRAM = """flowchart LR
  DEV[Local] --> IMG["Container<br/>index baked in"]
  IMG --> CR["Cloud Run<br/>--session-affinity"]
  SM["Secret Manager<br/>OPENAI_API_KEY"] --> CR
  GCS["GCS volume<br/>checkpoints"] --> CR
  CR --> USER[Browser]
"""


def architecture() -> None:
    st.title("Architecture")
    st.caption("The first diagram is generated from the compiled LangGraph, so it cannot "
               "drift from the code. The rest are maintained by hand.")

    deps = get_deps()
    from src.workflow.graph import FintorWorkflow

    st.subheader("1 · Workflow graph (generated)")
    st.caption("`compiled.get_graph().draw_mermaid()`")
    _mermaid(FintorWorkflow(deps).mermaid())

    st.subheader("2 · System architecture")
    _mermaid(SYSTEM_DIAGRAM)

    st.subheader("3 · Module dependency rule")
    st.caption("One-way only. `tests/test_architecture.py::test_no_upward_imports` fails the "
               "build if any module imports from a layer above it.")
    _mermaid(MODULE_DIAGRAM)

    st.subheader("4 · Retrieval pipeline")
    _mermaid(RAG_DIAGRAM)

    st.subheader("5 · Caching and cost control")
    _mermaid(CACHE_DIAGRAM)

    st.subheader("6 · Persona conditioning")
    _mermaid(PERSONA_DIAGRAM)

    st.subheader("7 · Deployment topology (planned)")
    _mermaid(DEPLOY_DIAGRAM)


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Separate YAML frontmatter from the body.

    Required because Markdown reads the closing `---` as a setext underline and
    turns the whole frontmatter block into an H1 - so the Governance page rendered
    "name: ai-grounding description: ..." as a headline.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip().strip("'\"")
    return meta, parts[2].lstrip()


def _render_skill(path: Path) -> None:
    """A skill file: its frontmatter as a header, its body as prose."""
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    if meta.get("name"):
        st.subheader(meta["name"])
    if meta.get("description"):
        st.caption(meta["description"])
    st.markdown(f'<div class="fin-prose">\n\n{body}\n\n</div>', unsafe_allow_html=True)


def _render_markdown_file(path: Path, *, download_label: str) -> None:
    """Rendered inside .fin-prose: these pages are read top to bottom, and the
    1120px content measure is still too wide for running text."""
    if not path.exists():
        st.info(f"`{path.name}` has not been written yet.")
        return
    text = path.read_text(encoding="utf-8")
    st.download_button(download_label, text, file_name=path.name, mime="text/markdown")
    st.markdown(f'<div class="fin-prose">\n\n{text}\n\n</div>', unsafe_allow_html=True)


def design() -> None:
    st.title("Design Document")
    st.caption("Rendered from `docs/design.md`. The README links here rather than duplicating it.")
    _render_markdown_file(ROOT / "docs" / "design.md", download_label="Download design.md")
    with st.expander("Implementation plan (docs/PLAN.md)"):
        _render_markdown_file(ROOT / "docs" / "PLAN.md", download_label="Download PLAN.md")


def governance() -> None:
    st.title("Governance")
    st.caption("AI guardrails as repository artifacts, in GitHub Copilot customization format. "
               "These constrain the code Claude writes, which is why they were committed first.")

    skills_dir = ROOT / ".github" / "skills"
    skills = sorted(skills_dir.glob("*/SKILL.md")) if skills_dir.exists() else []
    st.metric("Active skills", len(skills))

    tabs = st.tabs([p.parent.name for p in skills] + ["copilot-instructions", "Traceability"])
    for tab, path in zip(tabs, skills, strict=False):
        with tab:
            _render_skill(path)
    with tabs[len(skills)]:
        _render_markdown_file(ROOT / ".github" / "copilot-instructions.md",
                             download_label="Download copilot-instructions.md")
    with tabs[len(skills) + 1]:
        st.caption("Each acceptance criterion maps to a named test. A criterion with no "
                   "passing test stays Draft.")
        _render_markdown_file(ROOT / "specs" / "traceability.md",
                             download_label="Download traceability.md")
        specs = sorted((ROOT / "specs").glob("[0-9]*.md"))
        with st.expander(f"All specs ({len(specs)})"):
            for s in specs:
                st.markdown(f"**{s.name}**")
                st.markdown(s.read_text(encoding="utf-8"))
                st.divider()


def recording() -> None:
    st.title("Recording")
    st.caption("Demo walkthrough.")
    for candidate in ("docs/demo.mp4", "docs/demo.mov", "docs/recording.mp4"):
        path = ROOT / candidate
        if path.exists():
            st.video(str(path))
            return
    st.info("No recording yet. Drop a file at `docs/demo.mp4` and it will appear here.")
    st.markdown("""
**Suggested shot list** — one beat per rubric line:

1. **Persona switch** — ask *"Should I buy more NVDA?"* as **Dev** (70% concentrated), then as
   **Walter** (four years from retirement). Same agents, same corpus, different answers.
2. **Multi-agent fan-out** — *"How are capital gains taxed and how is SPY doing?"* → two agents
   run concurrently, sections merge, citations renumber.
3. **Tool calling** — *"What is AAPL trading at over 3 months?"* → the ReAct loop calls
   `get_quote` then `get_price_history`.
4. **Grounding** — show AI Internals: retrieval candidates with dense/BM25 ranks and RRF scores.
5. **Caching** — ask the same question twice; watch the cache tier flip to `exact` at zero cost.
6. **Guardrails** — an off-topic question gets refused with no LLM call at all.
7. **Governance** — the five SKILL.md files and the traceability matrix.
""")
