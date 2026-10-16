"""The app entry point actually runs, and its navigation keeps its shape.

These exist because a page-by-page probe missed a startup failure: two pages were
both backed by a callable named `render`, so Streamlit inferred the same URL for
each and st.navigation raised. Calling the page functions directly never touched
that, and an HTTP check could not see it either - Streamlit serves the same shell
for every path. Everything here goes through `app.py`.
"""

from __future__ import annotations

import ast
import re
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "web_app" / "app.py"
WEB_APP = ROOT / "src" / "web_app"


def _page_spec() -> list[tuple[str, str, str]]:
    """Read PAGE_SPEC out of app.py as (section, title, url_path), without importing
    Streamlit."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        if not any(isinstance(t, ast.Name) and t.id == "PAGE_SPEC" for t in targets):
            continue
        rows = []
        for element in node.value.elts:  # type: ignore[union-attr]
            vals = [e.value if isinstance(e, ast.Constant) else None for e in element.elts]
            rows.append((vals[0], vals[1], vals[2]))
        return rows
    raise AssertionError("PAGE_SPEC not found in app.py")


def _navigation_kwargs() -> dict:
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "navigation"):
            return {kw.arg: kw.value.value for kw in node.keywords
                    if kw.arg and isinstance(kw.value, ast.Constant)}
    raise AssertionError("st.navigation call not found in app.py")


# --- navigation shape ---------------------------------------------------


def test_navigation_uses_top_position():
    """A silent revert to the sidebar should fail the build, not just look different."""
    assert _navigation_kwargs().get("position") == "top"


def test_workspace_pages_are_ungrouped():
    """The five workspace pages must carry "" as their section.

    Labelling that group collapses all five into a dropdown and the top bar loses
    its tabs entirely - a visual regression that no other test would catch.
    """
    workspace = [r for r in _page_spec() if r[0] == ""]
    assert [r[1] for r in workspace] == ["Chat", "Portfolio", "Market", "Goals", "AI Internals"]


def test_about_pages_share_one_group():
    """Four reference pages, one labelled dropdown - not four fragments."""
    groups = {r[0] for r in _page_spec() if r[0]}
    assert groups == {"About Fintor"}
    about = [r[1] for r in _page_spec() if r[0] == "About Fintor"]
    assert len(about) == 4


def test_every_page_declares_an_explicit_url_path():
    """Inferred paths collide silently; explicit ones cannot."""
    missing = [title for _section, title, path in _page_spec() if not path]
    assert not missing, f"pages without an explicit url_path: {missing}"


def test_page_url_paths_and_titles_are_unique():
    spec = _page_spec()
    paths = [r[2] for r in spec]
    titles = [r[1] for r in spec]
    assert len(paths) == len(set(paths)), f"duplicate url_path: {paths}"
    assert len(titles) == len(set(titles)), f"duplicate titles: {titles}"


def test_no_sidebar_writes_anywhere():
    """There is no sidebar. That is the entire point of the layout change."""
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in WEB_APP.rglob("*.py")
        if "st.sidebar" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"st.sidebar used in: {offenders}"


def test_views_package_is_not_named_pages():
    """Streamlit auto-discovers a `pages/` directory beside the entrypoint, and the
    gate creates a path where st.navigation never runs to suppress it."""
    assert not (WEB_APP / "pages").exists(), "src/web_app/pages/ would be auto-discovered"
    assert (WEB_APP / "views").is_dir()


# --- brand assets -------------------------------------------------------


def test_brand_assets_exist_and_are_committed():
    from src.web_app.brand import FAVICON_PATH, LOGO_PATH, MARK_PATH

    for path in (MARK_PATH, LOGO_PATH, FAVICON_PATH):
        assert path.exists(), f"missing brand asset: {path}"
        assert path.stat().st_size > 0


def test_favicon_matches_the_svg_geometry():
    """The PNG and the SVG come from one point list, so a change to the mark
    cannot update one renderer and leave the other behind.

    This used to compare rectangles. The mark is a leaf now, with curves, and
    the easy thing would have been to delete the check along with the rects -
    but the invariant it protects is renderer agreement, not rectangles, and
    that still holds: the SVG emits LEAF as `points`, Pillow draws the same
    tuples.
    """
    from src.web_app.brand import LEAF, favicon_png, mark_svg

    svg = mark_svg()
    for x, y in LEAF:
        assert f"{x},{y}" in svg, f"point ({x},{y}) is missing from the SVG"
    assert favicon_png(32)[:8] == b"\x89PNG\r\n\x1a\n"


# --- the gate -----------------------------------------------------------


@pytest.mark.slow
def test_gate_blocks_until_persona_chosen():
    """With no persona set, the gate renders and the app does not.

    This is the one that catches a gate that draws itself but lets execution fall
    through into the app anyway.
    """
    import os

    os.environ["FINTOR_OFFLINE"] = "1"
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=300)
    at.run()
    assert not at.exception, at.exception[0].value if at.exception else ""

    body = "\n".join(m.value for m in at.markdown)
    assert "Sign in" in body or "not configured" in body, "the gate did not render"
    assert "Finance, taught." in body
    assert not at.title, "no page title should render behind the gate"
    assert "Demo accounts" in body or "not configured" in body


@pytest.mark.slow
def test_gate_passes_once_persona_set():
    import os

    os.environ["FINTOR_OFFLINE"] = "1"
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=300)
    at.session_state["persona_id"] = "dev"
    at.run()
    assert not at.exception, at.exception[0].value if at.exception else ""
    assert [t.value for t in at.title] == ["Ask Fintor"], "Chat should be the default page"
    body = "\n".join(m.value for m in at.markdown)
    assert "Who are you today?" not in body, "the gate should be gone"
    # Chat is a workspace page, so it deliberately has NO breadcrumb - the solid
    # green Chat tab already says where you are.
    assert 'class="bc"' not in body, "workspace pages should not render a breadcrumb"
    assert "ident-who" in body, "the identity readout should be in the header"


def test_the_dead_passcode_setting_is_gone():
    """FINTOR_PASSCODE was the old shared gate. The username+password sign-in
    replaced it and nothing read it any more - but it was still a documented
    setting, so an operator could set it, believe the app was protected, and be
    wrong. A security control that silently does nothing is worse than none.
    """
    from src.core.config import Settings, load_settings

    assert not hasattr(load_settings(), "passcode")
    assert "passcode" not in {f for f in Settings.__dataclass_fields__}
    for path in (ROOT / "src").rglob("*.py"):
        assert "FINTOR_PASSCODE" not in path.read_text(encoding="utf-8"), \
            f"{path.name} still reads the removed passcode"
    assert "FINTOR_PASSCODE" not in (ROOT / ".env.example").read_text(encoding="utf-8")


@pytest.mark.slow
def test_app_entrypoint_runs_without_exception():
    """The check that would have caught the url_path collision."""
    import os

    os.environ["FINTOR_OFFLINE"] = "1"
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=300)
    at.session_state["persona_id"] = "maya"
    at.run()
    assert not at.exception, at.exception[0].value if at.exception else ""


# --- breadcrumb ---------------------------------------------------------


def test_breadcrumb_only_renders_where_there_is_depth():
    """Workspace pages no longer show a breadcrumb at all.

    "Fintor / Chat" beside a solid-green Chat tab states the same fact twice. The
    About group has real depth the tabs do not show, so it keeps the trail.
    """
    import ast

    from src.web_app.chrome import breadcrumb

    grouped = breadcrumb("About Fintor", "Governance")
    assert grouped.count("<li>") == 3, "Fintor / About Fintor / Governance is three"
    assert "About Fintor" in grouped
    assert 'aria-current="page"' in grouped

    # header() must gate on the group rather than always rendering.
    src = (WEB_APP / "chrome.py").read_text(encoding="utf-8")
    header = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "header")
    guards = [n for n in ast.walk(header)
              if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "group"]
    assert guards, "header() renders the breadcrumb unconditionally"


def test_breadcrumb_ancestors_are_not_links():
    """A breadcrumb with dead links is worse than one with none."""
    from src.web_app.chrome import breadcrumb

    assert "<a " not in breadcrumb("About Fintor", "Governance")


def test_favicon_resolves_to_a_real_icon_string():
    """The check that caught the favicon being silently dropped.

    Streamlit routes paths, PIL images, and bytes through its media pipeline, all of
    which resolved to an empty string - meaning the browser quietly fell back to the
    default Streamlit mark. A data URI is accepted directly. Asserting non-empty is
    the difference between "we passed an icon" and "an icon is actually used".
    """
    from streamlit.commands.page_config import _get_favicon_string

    from src.web_app.brand import FAVICON_PATH, favicon_data_uri

    resolved = _get_favicon_string(favicon_data_uri())
    assert resolved, "favicon resolved to empty - it would be silently dropped"
    assert resolved.startswith("data:image/png;base64,")

    # And the form that does NOT work stays documented by a test, so nobody
    # "simplifies" it back to a path.
    assert not _get_favicon_string(str(FAVICON_PATH)), (
        "a path now resolves - the data-URI workaround may no longer be needed"
    )


@pytest.mark.slow
def test_gate_does_not_build_the_container():
    """Painting a sign-in screen must not load the embedder and the retrieval index.

    Asserted by making the container explode: if the gate still renders, it is not
    reaching for it. A timing comparison would not prove this - caches confound it.
    """
    import os

    os.environ["FINTOR_OFFLINE"] = "1"
    from streamlit.testing.v1 import AppTest

    probe = (
        "import sys, os\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "os.environ['FINTOR_OFFLINE'] = '1'\n"
        "import src.container as container\n"
        "def _boom(*a, **k):\n"
        "    raise AssertionError('the gate built the container')\n"
        "container.build = _boom\n"
        "exec(open(%r).read())\n" % str(APP)
    )
    at = AppTest.from_string(probe, default_timeout=300)
    at.run()
    assert not at.exception, at.exception[0].value if at.exception else ""
    body = "\n".join(m.value for m in at.markdown)
    assert "Finance, taught." in body, "gate did not render with the container disabled"


# --- the workspace is a workspace, not a document -----------------------


def _workspace_src() -> str:
    return (ROOT / "src" / "web_app" / "views" / "workspace.py").read_text(encoding="utf-8")


def test_every_workspace_page_uses_the_main_and_rail_split():
    """A single stacked column reads as a document. The rail is the structural
    difference that no amount of chart polish was going to close."""
    src = _workspace_src()
    assert src.count("main_and_rail()") == 3, "all three pages need the split"


def test_every_figure_sits_inside_a_card():
    """A chart floating on the page with a bare heading above it was the
    "surfaces" gap. Each plotly_chart must be lexically inside a `with card(`.
    """
    import ast

    src = _workspace_src()
    tree = ast.parse(src)
    charted: list[int] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "plotly_chart"):
            charted.append(node.lineno)
    assert charted, "expected charts in workspace.py"

    card_spans = [
        (item.context_expr.lineno, node.end_lineno)
        for node in ast.walk(tree) if isinstance(node, ast.With)
        for item in node.items
        if isinstance(item.context_expr, ast.Call)
        and getattr(item.context_expr.func, "id", "") == "card"
    ]
    for line in charted:
        assert any(start <= line <= end for start, end in card_spans), \
            f"the chart at line {line} is not inside a card"


def test_what_this_shows_requires_a_stated_limitation():
    """The keyword-only `ignores` is a forcing function: a figure that explains
    itself but not its limits is the more dangerous of the two."""
    import inspect

    from src.web_app.components import what_this_shows

    params = inspect.signature(what_this_shows).parameters
    assert params["ignores"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["ignores"].default is inspect.Parameter.empty, "must be required"

    with pytest.raises(ValueError, match="ignores"):
        what_this_shows("a point", ignores="   ")


def test_every_chart_card_carries_a_what_this_shows():
    """Three figures explain themselves; the allocation bar is self-labelling
    and sits under a titled card, so it is the deliberate exception."""
    src = _workspace_src()
    assert src.count("what_this_shows(") == 4, \
        "a figure was added or removed without its explanation block"


def test_answer_text_escapes_currency_so_it_is_not_read_as_latex():
    """Observed live: "worth about $90,184, including $12,000 in cash" rendered
    the span between the two amounts as inline maths. For a finance assistant,
    two currency amounts in a sentence is the common case, not the edge case.
    """
    from src.web_app.components import escape_dollars

    out = escape_dollars("worth about $90,184, including $12,000 in cash")
    assert out.count(r"\$") == 2
    assert "$9" not in out.replace(r"\$", "")


def test_escaping_currency_is_idempotent():
    """It runs on stored turns on every rerun, so it must not accumulate."""
    from src.web_app.components import escape_dollars

    once = escape_dollars("$5 and $6")
    assert escape_dollars(once) == once


def test_every_render_of_answer_text_goes_through_the_escape():
    """A second render path that skips it brings the bug straight back."""
    import ast

    src = (ROOT / "src" / "web_app" / "views" / "chat.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "markdown" and node.args):
            rendered = ast.unparse(node.args[0])
            if '"text"' in rendered or "'text'" in rendered:
                assert rendered.startswith("escape_dollars("), \
                    f"unescaped answer text at line {node.lineno}: {rendered}"


# --- diagrams size themselves ---------------------------------------------


def test_no_view_hardcodes_a_diagram_height():
    """Measured in the browser with the old fixed heights: two of seven
    diagrams were clipped (the caching one lost 453px of 1027) and four wasted
    142-354px of dead space. Not one of the seven guesses was right.

    `st_mermaid` already defaults to height="auto" and its frontend calls
    setFrameHeight(bbox.height + 16) after rendering, so passing a number was
    overriding a mechanism that already worked. Swept over every view, because
    the previous pass fixed one page and left the same defect in another.
    """
    import ast

    offenders = []
    for path in (ROOT / "src" / "web_app" / "views").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name not in {"st_mermaid", "_mermaid"}:
                continue
            for kw in node.keywords:
                if kw.arg == "height":
                    offenders.append(f"{path.name}:{node.lineno}")
            for arg in node.args[1:]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and arg.value.endswith("px"):
                    offenders.append(f"{path.name}:{node.lineno} (positional)")
    assert not offenders, "hardcoded diagram height at " + ", ".join(offenders)


def test_the_mermaid_wrapper_takes_no_height_argument():
    """The guard above only works if there is no parameter to pass."""
    import inspect

    from src.web_app.views.about import _mermaid

    assert "height" not in inspect.signature(_mermaid).parameters


def test_the_generated_graph_is_laid_out_horizontally():
    """LangGraph emits top-down, which for this graph is a 157x616 ribbon -
    16% of the width of the column it sits in, and 122px taller than its frame.
    """
    from src.workflow.graph import FintorWorkflow

    # A stub, not container.build(): an earlier test patches build() to assert
    # the gate never constructs the container, and that patch leaks here. The
    # graph's SHAPE does not depend on deps anyway - only its nodes do.
    class _Stub:
        settings = type("S", (), {"workflow": {"agent_timeout_seconds": 5}})()
        agents: dict = {}
        router = None

    code = FintorWorkflow(_Stub()).mermaid()
    # draw_mermaid() opens with a --- config block, so the direction token is
    # not on line 1; match it wherever it lands.
    assert "graph TD" not in code and "flowchart TD" not in code
    assert "graph LR" in code or "flowchart LR" in code, code.splitlines()[:6]
    for node in ("guard", "router", "agent", "synthesize", "verify"):
        assert node in code, f"{node} vanished from the generated diagram"


# --- the mark has to survive at the size it is used ------------------------


def _render_mark(size: int = 32):
    """The mark as a boolean grid, drawn exactly as favicon_png draws it."""
    from PIL import Image, ImageDraw

    from src.web_app.brand import GRID, LEAF

    scale = size / GRID
    img = Image.new("L", (size, size), 0)
    ImageDraw.Draw(img).polygon([(x * scale, y * scale) for x, y in LEAF], fill=255)
    return [[img.getpixel((x, y)) > 127 for x in range(size)] for y in range(size)]


def test_the_mark_has_enough_weight_to_read_small():
    """It renders at 34px in the header and 24px before that. The old version
    of this test asserted stem and bar widths, which mean nothing for a leaf -
    but what those numbers were really protecting is that the mark has enough
    mass to survive at the size it is actually used. Ink coverage says the same
    thing about any shape.
    """
    grid = _render_mark(32)
    ink = sum(row.count(True) for row in grid)
    coverage = ink / (32 * 32)
    assert coverage >= 0.35, f"the mark covers {coverage:.0%}; it will read as a smudge"
    assert coverage <= 0.85, f"the mark covers {coverage:.0%}; it is a blob, not a mark"


def test_the_midrib_gap_survives_at_favicon_size():
    """The gap is what makes it a leaf rather than a blob. It is the first
    feature to close when the shape is scaled down, so it is checked at the
    smallest size the app actually renders.

    A row crossing the shape four times means ink, gap, ink - the midrib.
    """
    for size in (32, 16):
        grid = _render_mark(size)
        split_rows = 0
        for row in grid:
            runs, prev = 0, False
            for cell in row:
                if cell and not prev:
                    runs += 1
                prev = cell
            if runs >= 2:
                split_rows += 1
        assert split_rows >= 2, (
            f"at {size}px no row shows a midrib gap; the leaf has closed into a blob")


def test_a_dark_wordmark_is_committed_and_differs():
    """An <img> cannot inherit CSS colour, so the dark lockup is its own file."""
    from src.web_app.brand import LOGO_DARK_PATH, LOGO_PATH

    assert LOGO_DARK_PATH.exists() and LOGO_DARK_PATH.stat().st_size > 0
    assert LOGO_DARK_PATH.read_text() != LOGO_PATH.read_text(), \
        "the dark logo is identical to the light one"


def test_the_header_is_fed_the_wordmark_not_the_bare_mark():  # noqa: D401
    """With no sidebar Streamlit renders the icon_image slot. Passing MARK_PATH
    there meant the header showed a 24px glyph and the wordmark never appeared
    at all - which read as "the logo text is missing", because it was.
    """
    src = (ROOT / "src" / "web_app" / "app.py").read_text(encoding="utf-8")
    call = re.search(r"st\.logo\(([^)]*)\)", src)
    assert call, "no st.logo call"
    assert "MARK_PATH" not in call.group(1), \
        "the bare mark is back in the logo slot; the wordmark will not render"
    assert "icon_image" in call.group(1), "icon_image is the slot that renders"


def test_the_gate_wordmark_follows_the_theme_without_a_rerun():
    """The gate inlines the SVG, so CSS reaches into it - unlike the header,
    which goes through <img> and needs two files plus a rerun to swap."""
    src = (ROOT / "src" / "web_app" / "gate.py").read_text(encoding="utf-8")
    assert 'logo_svg(ink="currentColor")' in src


def test_the_sign_in_screen_hides_the_stale_top_nav():
    """On sign-out the script reruns, the gate calls st.stop() before
    st.navigation(), and Streamlit never sends an update to clear the tabs the
    previous run painted - so the app's navigation sits above the login screen.

    It is cosmetic, not a bypass: clicking a stale tab renders no page because
    st.stop() still runs. But a login screen wearing the app's nav implies you
    are already half way in, so the gate hides it.
    """
    from src.web_app.gate import GATE_CHROME_CSS

    assert "stTopNavLinkContainer" in GATE_CHROME_CSS
    assert "stTopNavSection" in GATE_CHROME_CSS
    assert "stLogoLink" in GATE_CHROME_CSS
    assert "stToolbar" not in GATE_CHROME_CSS, \
        "leave the toolbar alone - the theme switcher lives there"
