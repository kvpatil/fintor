"""About Fintor: Architecture, Design Document, Governance, Recording."""

from __future__ import annotations

import html
import os
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

def _rag_diagram() -> str:
    """Built from config.yaml rather than hard-coded.

    The numbers in this diagram - the overfetch depth, the RRF constant, the
    refusal threshold - used to be typed into the Mermaid string. They matched
    config at the time and would have gone stale silently the first time
    anyone tuned retrieval, on the one page whose whole job is to describe how
    retrieval works. Reading the same keys the retriever reads means the
    diagram cannot be wrong.
    """
    from src.web_app.state import app_settings

    rag = app_settings().rag
    k = int(rag.get("overfetch", 20))
    rrf_k = int(rag.get("rrf_k", 60))
    floor = float(rag.get("score_threshold", 0.25))
    return f"""flowchart LR
  Q[Question] --> E[Embed]
  Q --> B[BM25 tokenize]
  E --> D[Dense top-{k}]
  B --> S[Sparse top-{k}]
  D --> F["RRF fuse<br/>k={rrf_k}"]
  S --> F
  F --> C[Recompute cosine]
  C --> DF["Difficulty + category filter<br/>(persona)"]
  DF --> G{{"score >= {floor}?"}}
  G -->|no| R["Refuse<br/>no LLM call"]
  G -->|yes| P[Numbered passages to LLM]
  P --> V["Verify [n] markers"]
"""


# All SEVEN caches, which is what the code actually has. This diagram used to
# show two of them - "Layer 1" and "Layer 4" - while internals.py named three
# and config.yaml said seven: a three-way disagreement on the page whose job
# is to be the reference. The four LLM tiers are the CacheTier members
# (exact, semantic, prompt, offline); the other three are the embedding,
# market-data and news caches.
CACHE_DIAGRAM = """flowchart TB
  A[Request] --> BG{"Budget left?"}
  BG -->|no| K["BudgetExceeded<br/>kill switch"]
  BG -->|yes| OFF{"Offline mode?"}
  OFF -->|yes| L0["4 · offline<br/>canned, never billed"]
  OFF -->|no| L1{"1 · exact prompt<br/>on disk?"}
  L1 -->|hit| Z["Return, 0 tokens"]
  L1 -->|miss| L2{"2 · semantic<br/>paraphrase match?"}
  L2 -->|hit| Z
  L2 -->|miss| P["Provider call<br/>3 · prompt prefix cache"]
  P --> R[Record CostRecord]

  EMB["5 · embedding cache<br/>corpus embedded once"] -.-> P
  MKT["6 · market cache<br/>quotes 30m, history 6h"] -.-> P
  NWS["7 · news cache<br/>headlines TTL"] -.-> P
"""

PERSONA_DIAGRAM = """flowchart LR
  PS[Persona selected] --> PP[Prompt preamble<br/>experience level + risk]
  PS --> DC[Difficulty ceiling<br/>corpus filter]
  PS --> TH["thread_id<br/>isolated checkpoint"]
  PP --> ANS[Answer]
  DC --> ANS
  TH --> ANS
"""

# The GCS-volume arrow is gone. It showed SQLite checkpoints on a GCS FUSE
# mount, which is a corruption path - WAL mode needs POSIX locking that
# network filesystems do not provide. State is per-instance instead, and the
# consequence (caches and transcripts lost on recycle) is documented rather
# than papered over. See docs/deploy.md.
DEPLOY_DIAGRAM = """flowchart LR
  DEV[Local] --> IMG["Container<br/>index + model baked in"]
  IMG --> CR["Cloud Run<br/>session affinity<br/>no CPU throttling"]
  SM["Secret Manager<br/>API key · password · session secret"] --> CR
  CR --> USER[Browser]
  CR -.-> EXT["OpenAI · Yahoo Finance · Langfuse"]
  ST["Per-instance state<br/>caches + threads<br/>lost on recycle"] -.-> CR
"""


def architecture(*, generated: bool = True) -> None:
    """The seven diagrams.

    `generated=False` drops the first one, which is the only part of this page
    that needs the container: drawing it builds the embedder and loads the
    retrieval index. The pre-auth shell passes False, because state.py is
    explicit that the container is not for unauthenticated callers - and on
    Cloud Run an anonymous visitor could otherwise trigger an index load per
    page view. The other six are static strings and a config read.
    """
    st.title("Architecture")
    if generated:
        st.caption("The first diagram is generated from the compiled LangGraph, so it "
                   "cannot drift from the code. The rest are maintained by hand.")

        deps = get_deps()
        from src.workflow.graph import FintorWorkflow

        st.subheader("1 · Workflow graph (generated)")
        st.caption("`compiled.get_graph().draw_mermaid()`")
        _mermaid(FintorWorkflow(deps).mermaid())
    else:
        st.caption("These are maintained by hand. The compiled LangGraph is drawn from "
                   "the running system, so it appears here once you are signed in.")

    st.subheader("2 · System architecture")
    _mermaid(SYSTEM_DIAGRAM)

    st.subheader("3 · Module dependency rule")
    st.caption("One-way only. `tests/test_architecture.py::test_no_upward_imports` fails the "
               "build if any module imports from a layer above it.")
    _mermaid(MODULE_DIAGRAM)

    st.subheader("4 · Retrieval pipeline")
    _mermaid(_rag_diagram())

    st.subheader("5 · Caching and cost control")
    _mermaid(CACHE_DIAGRAM)

    st.subheader("6 · Persona conditioning")
    _mermaid(PERSONA_DIAGRAM)

    st.subheader("7 · Deployment topology")
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
    # docs/PLAN.md is NOT rendered here, and that is deliberate. It is a
    # working planning document: it contains the assignment's grading rubric,
    # the brand's naming rationale, and a teardown of a competing
    # implementation including its test count. All reasonable things for a
    # repo to hold and none of them things to show a user inside the product.
    # It is still in the repository for anyone reading the source.


def governance() -> None:
    st.title("Governance")
    st.caption("The rules this system is built to follow - what it will not generate, "
               "how every figure is grounded, and how spend is bounded. They are "
               "committed alongside the code and enforced by the test suite.")

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

    # A URL wins over a local file when both are available.
    #
    # .dockerignore keeps the 29 MB mp4 out of the image on purpose, so in a
    # container there is no local file to find and this page used to render its
    # "no recording" fallback - the one page a reviewer of a DEPLOYED build is
    # most likely to open. Cloud Run reads the object from Cloud Storage
    # instead, which is better than baking it in regardless of size: the
    # browser streams it and can seek (the bucket answers byte-range requests
    # with a 206), where the data-URI path below has to transfer all 41 MB of
    # base64 before the first frame.
    url = os.environ.get("FINTOR_DEMO_VIDEO_URL", "").strip()
    if url:
        _play_url(url)
        return

    for candidate in ("docs/demo.mp4", "docs/demo.mov", "docs/recording.mp4"):
        path = ROOT / candidate
        if path.exists():
            _play(path)
            return

    # The fallback used to carry a seven-beat shot list, each beat labelled
    # with the grading criterion it was meant to satisfy. That is production
    # notes for the author, visible to anyone who clones the repo without the
    # video file.
    st.info("No recording has been added to this build. Drop a file at "
            "`docs/demo.mp4` and it will appear here.")


def _play_url(url: str) -> None:
    """Stream from a URL. No bytes pass through this process.

    st.video() is still avoided here for the reason in _play(): it routes
    through Streamlit's media endpoint even for a remote source. A plain
    <video src> lets the browser fetch the object directly, so the container
    never holds the file and the page stays small.
    """
    st.markdown(
        f'<video controls preload="metadata" style="width:100%;border-radius:10px;"'
        f' src="{html.escape(url, quote=True)}">'
        f'Your browser cannot play this video.</video>',
        unsafe_allow_html=True,
    )
    st.link_button("Download the walkthrough", url)


def _play(path) -> None:
    """Render the video WITHOUT st.video().

    st.video hands the file to Streamlit's media endpoint, which returns 500
    in this environment - the uvicorn/gzip middleware raises "Expected ASGI
    message http.response.start" and the browser gets MEDIA_ERR_SRC_NOT_
    SUPPORTED. Measured both forms: a path and raw bytes fail identically,
    because both route through the same endpoint. It is the third thing that
    endpoint has broken here, after the favicon and the header logo.

    So the bytes are embedded directly in a plain <video> element. The 29 MB
    mp4 is roughly 41 MB of base64 in the page, which is heavy but paid once
    on a page nobody reloads in a loop - and it needs no media endpoint, so
    it cannot be dropped by one. Measured at that size: the player reaches
    readyState 4 and reports the full 9:21, so the data URI is not hitting a
    browser length limit. Worth re-checking if the video grows much past this.

    The download button is not decoration: it uses the same bytes and gives
    a reviewer a way to watch the file in a real player if the embedded one
    misbehaves in their browser.
    """
    import base64

    data = path.read_bytes()
    size_mb = len(data) / 1e6
    uri = "data:video/mp4;base64," + base64.b64encode(data).decode("ascii")

    st.markdown(
        f'<video controls preload="metadata" style="width:100%;border-radius:10px;"'
        f' src="{uri}">Your browser cannot play this video.</video>',
        unsafe_allow_html=True,
    )
    st.download_button(f"Download the walkthrough ({size_mb:.0f} MB)", data=data,
                       file_name=path.name, mime="video/mp4")


# --- what is readable without signing in --------------------------------
# Keyed by the same url_path values app.py's PAGE_SPEC uses, so a renamed
# route cannot leave this mapping pointing at nothing - test_app_pages.py
# asserts the keys are a subset of PAGE_SPEC's paths.
#
# Everything these four pages render is already public: docs/design.md,
# .github/skills/*, specs/* and docs/demo.mp4 are committed to the repository,
# the walkthrough is linked from the README, and the Cloud Storage object
# answers an anonymous GET. The gate in front of them was guarding content
# with no lock behind it, and a reviewer of a deployed build should not have
# to authenticate to read the design document.
#
# AI Internals is deliberately ABSENT. It shares the "About Fintor" nav group
# but it is a readout of the LAST RUN - routing tier, retrieval ranks, token
# ledger - which an anonymous visitor has none of, so it would render empty
# and it reports session activity besides. The exclusion is tested.
#
# Architecture is bound with generated=False: see its docstring.
PUBLIC_PAGES: dict[str, tuple[str, object]] = {
    "architecture": ("Architecture", lambda: architecture(generated=False)),
    "design": ("Design Document", design),
    "governance": ("Governance", governance),
    "recording": ("Recording", recording),
}
