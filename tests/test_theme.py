"""Theme fitness functions.

The small font sizes in this app drifted down to 11.5px by being chosen one rule at
a time, and the dark theme shipped with near-black text because two values were
never tokenised. Both are the kind of defect a human notices and a test does not -
unless the test is written to look for exactly that shape of mistake.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from src.web_app.theme import CSS

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".streamlit" / "config.toml"

FLOOR_REM = 0.875  # 14px at a 16px base


# --- type scale ---------------------------------------------------------


def test_no_font_size_below_the_floor():
    """Nothing under 14px anywhere in the stylesheet.

    This is the regression guard. The sizes reached 11.5px gradually, each one
    defensible on its own; a floor makes the next such step fail the build.
    """
    offenders = [
        (match, float(re.search(r"[0-9.]+", match).group(0)) * 16)
        for match in re.findall(r"font-size:\s*[0-9.]+rem", CSS)
        if float(re.search(r"[0-9.]+", match).group(0)) < FLOOR_REM
    ]
    assert not offenders, "font sizes below 14px: " + ", ".join(
        f"{m} ({px:.1f}px)" for m, px in offenders
    )


def test_scale_tokens_are_defined_and_used():
    """Small text goes through tokens, so the floor cannot be bypassed by a literal."""
    for token, expected in (("--fs-xs", "0.875rem"), ("--fs-sm", "0.9375rem"),
                            ("--fs-md", "1rem")):
        assert f"{token}: {expected}" in CSS, f"{token} missing or changed value"
        assert f"var({token})" in CSS, f"{token} defined but never used"


@pytest.mark.parametrize("selector", [
    ".chip", ".fin-chip", ".gate-ask", ".gate-nums", ".gate-meta",
    ".gate-foot", ".prompt-hint", ".fin-cite", ".ident-who",
])
def test_small_text_rules_use_a_token(selector):
    """Each secondary-text rule sizes itself from the scale, not a raw value."""
    pattern = re.escape(selector) + r"[^{]*\{([^}]*)\}"
    block = re.search(pattern, CSS)
    assert block, f"{selector} not found in CSS"
    body = block.group(1)
    if "font-size" in body:
        assert "var(--fs-" in body, f"{selector} sizes itself with a literal"


# --- layout -------------------------------------------------------------


def test_top_gap_is_tokenised():
    """The nav-to-content distance is tunable in one place.

    Streamlit sizes stMainBlockContainer's padding for an app with no top nav, so
    with position="top" it stacks below the bar rather than being absorbed.
    """
    assert "--fin-top-gap:" in CSS
    block = re.search(r'\[data-testid="stMainBlockContainer"\][^{]*\{([^}]*)\}', CSS)
    assert block, "no stMainBlockContainer override - the top gap will return"
    assert "var(--fin-top-gap)" in block.group(1)


# --- both themes --------------------------------------------------------


THEME_TOKENS = ("--fin-ink", "--fin-muted", "--fin-line", "--fin-accent",
                "--fin-warn", "--fin-paper")


@pytest.mark.parametrize("token", THEME_TOKENS)
def test_every_colour_token_is_redefined_for_dark(token):
    """A token that only exists in :root survives into dark mode unchanged.

    That is exactly how near-black --fin-ink and near-white --fin-paper ended up on
    a dark ground: they were styled through, but never overridden.
    """
    dark_media = re.search(r"@media \(prefers-color-scheme: dark\)\s*\{(.*?)\n\}", CSS, re.S)
    dark_attr = re.search(r':root\[data-theme="dark"\]\s*\{([^}]*)\}', CSS)
    assert dark_media and dark_attr, "dark theme blocks missing"
    assert token in dark_media.group(1), f"{token} not redefined under prefers-color-scheme"
    assert token in dark_attr.group(1), f'{token} not redefined under [data-theme="dark"]'


def test_light_theme_is_restored_explicitly():
    """The viewer's toggle must win in BOTH directions, so light is also explicit."""
    light = re.search(r':root\[data-theme="light"\]\s*\{([^}]*)\}', CSS)
    assert light, "no [data-theme=light] block - the toggle cannot override dark OS preference"
    for token in THEME_TOKENS:
        assert token in light.group(1), f"{token} missing from the light override"


def test_config_does_not_pin_a_single_palette():
    """`base` pins the app to one palette and ignores the viewer entirely."""
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    theme = config.get("theme", {})
    assert "base" not in theme, "theme.base pins the palette; use [theme.light]/[theme.dark]"
    assert "light" in theme and "dark" in theme, "both palettes must be declared"
    assert theme["light"]["backgroundColor"] != theme["dark"]["backgroundColor"]


# --- contrast -----------------------------------------------------------


def _luminance(hex_colour: str) -> float:
    """WCAG relative luminance."""
    h = hex_colour.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    a, b = _luminance(fg), _luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def _token(block_pattern: str, token: str) -> str:
    block = re.search(block_pattern, CSS, re.S)
    assert block, f"block not found for {token}"
    found = re.search(rf"{token}:\s*(#[0-9a-fA-F]{{6}})", block.group(1))
    assert found, f"{token} not found in block"
    return found.group(1)


def test_muted_contrast_passes_aa_on_both_grounds():
    """Darkening the light grey is the kind of change that quietly breaks dark mode,
    so both directions are measured rather than one assumed."""
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))

    light_muted = _token(r':root \{(.*?)\n\}', "--fin-muted")
    light_bg = config["theme"]["light"]["backgroundColor"]
    light_ratio = _contrast(light_muted, light_bg)

    dark_muted = _token(r':root\[data-theme="dark"\]\s*\{(.*?)\}', "--fin-muted")
    dark_bg = config["theme"]["dark"]["backgroundColor"]
    dark_ratio = _contrast(dark_muted, dark_bg)

    assert light_ratio >= 4.5, f"light muted {light_muted} on {light_bg} is {light_ratio:.2f}:1"
    assert dark_ratio >= 4.5, f"dark muted {dark_muted} on {dark_bg} is {dark_ratio:.2f}:1"


def test_accent_is_legible_on_its_own_ground():
    """The accent carries the eyebrows and the active breadcrumb, so it is text."""
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    light = _contrast(_token(r':root \{(.*?)\n\}', "--fin-accent"),
                      config["theme"]["light"]["backgroundColor"])
    dark = _contrast(_token(r':root\[data-theme="dark"\]\s*\{(.*?)\}', "--fin-accent"),
                     config["theme"]["dark"]["backgroundColor"])
    assert light >= 4.5, f"light accent contrast is {light:.2f}:1"
    assert dark >= 4.5, f"dark accent contrast is {dark:.2f}:1"


# --- governance page rendering -----------------------------------------


def test_skill_frontmatter_is_split_not_rendered():
    """Markdown reads a closing `---` as a setext underline, which turned each
    SKILL.md's YAML frontmatter into an H1 on the Governance page."""
    from src.web_app.views.about import split_frontmatter

    meta, body = split_frontmatter(
        "---\nname: ai-grounding\ndescription: 'Ground every answer'\n---\n\nYour goal is…"
    )
    assert meta["name"] == "ai-grounding"
    assert meta["description"] == "Ground every answer"
    assert not body.startswith("---"), "frontmatter leaked into the rendered body"
    assert body.startswith("Your goal")


def test_split_frontmatter_passes_through_plain_markdown():
    from src.web_app.views.about import split_frontmatter

    meta, body = split_frontmatter("# Heading\n\nNo frontmatter here.")
    assert meta == {}
    assert body.startswith("# Heading")


def test_every_shipped_skill_has_parseable_frontmatter():
    """The Governance page reads these at runtime; a malformed one renders as noise."""
    from src.web_app.views.about import split_frontmatter

    skills = sorted((ROOT / ".github" / "skills").glob("*/SKILL.md"))
    assert len(skills) == 5, f"expected 5 skills, found {len(skills)}"
    for path in skills:
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        assert meta.get("name"), f"{path.parent.name} has no name in frontmatter"
        assert meta.get("description"), f"{path.parent.name} has no description"
        assert body and not body.startswith("---"), f"{path.parent.name} body not split"


# --- top navigation -----------------------------------------------------


def test_nav_text_is_at_least_16px():
    """The nav was the one surface the body type floor never reached.

    It is Streamlit's own markup, so it stayed at the default 14px while
    everything around it grew. This stops it drifting back.
    """
    block = re.search(r'\[data-testid="stTopNavLink"\]\s*\{([^}]*)\}', CSS)
    assert block, "no stTopNavLink rule - the nav is back at Streamlit's default"
    assert "var(--fs-md)" in block.group(1), "nav label should use the 16px token"


def test_nav_icons_are_sized_explicitly():
    """Material icons are font ligatures: without a font-size they inherit 14px."""
    rule = re.search(
        r'\[data-testid="stTopNavLink"\] \[data-testid="stIconMaterial"\]\s*\{([^}]*)\}', CSS)
    assert rule, "nav icons have no explicit size rule"
    assert "font-size: 20px" in rule.group(1)


def test_nav_styles_target_stable_hooks():
    """Styling off Streamlit's generated class hashes breaks on every upgrade."""
    assert "st-emotion-cache-" not in CSS, "CSS depends on a generated emotion class"
    assert '[aria-current="page"]' in CSS, "active tab should key off aria-current"
    assert CSS.count("href$=") >= 3, "state dots should key off stable hrefs"


def test_nav_colour_tokens_are_defined_for_both_themes():
    for token in ("--tab-workspace", "--tab-reference", "--dot-live",
                  "--dot-cached", "--dot-attention"):
        assert f"{token}:" in CSS, f"{token} undefined"
        dark = re.search(r':root\[data-theme="dark"\]\s*\{([^}]*)\}', CSS)
        assert token in dark.group(1), f"{token} not redefined for dark"


# --- nav state dots -----------------------------------------------------


def test_dot_colour_mapping():
    """Cached is grey on purpose: a cached answer is honest, not a warning."""
    from src.core.contracts import DataStatus
    from src.web_app.chrome import dot_for

    assert dot_for(DataStatus.LIVE) == "var(--dot-live)"
    assert dot_for(DataStatus.CACHED) == "var(--dot-cached)"
    assert dot_for(DataStatus.STALE) == "var(--dot-attention)"
    assert dot_for(DataStatus.SAMPLE) == "var(--dot-attention)"


def test_no_dot_before_a_real_observation():
    """A green "live" dot that no provider earned is a lie.

    MarketService initialises last_status to LIVE so callers always have something
    to read; the nav must check `observed` instead of trusting it.
    """
    from src.core.contracts import DataStatus
    from src.web_app.chrome import dot_for

    assert dot_for(DataStatus.LIVE, observed=False) == "transparent"
    assert dot_for(None) == "transparent"


def test_market_service_starts_unobserved():
    from src.core.cache import MemoryCache
    from src.data.market import MarketService, MockProvider

    svc = MarketService([MockProvider()], MemoryCache())
    assert svc.observed is False, "a cold service must not claim an observation"
    svc.quotes(["AAPL"])
    assert svc.observed is True, "fetching quotes is an observation"


# --- text density -------------------------------------------------------


def test_chat_page_has_no_redundant_caption_or_info():
    """Both repeated something already on screen: the gate's subline, and the four
    prompt buttons directly above."""
    src = (ROOT / "src" / "web_app" / "views" / "chat.py").read_text(encoding="utf-8")
    assert "Six specialist agents, grounded" not in src, "the caption is back"
    assert "st.info(" not in src, "the redundant info box is back"


def test_nav_state_is_painted_after_the_page_body():
    """The dots must reflect what the page just did, not what was true before it ran.

    Painting inside header() - which renders before current.run() - made visiting
    Market show no dot, with the dot only appearing after navigating away.
    """
    import ast

    src = (ROOT / "src" / "web_app" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    order = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"run", "paint_nav_state", "header"}:
                order.append((node.lineno, node.func.attr))
    order.sort()
    names = [n for _, n in order]
    assert "paint_nav_state" in names, "nav state is never painted"
    assert names.index("paint_nav_state") > names.index("run"), (
        "paint_nav_state must come after current.run(), or the dots lag an interaction"
    )


# --- layout measure -----------------------------------------------------


def test_content_measure_is_constrained():
    """Without this the app is full-bleed and prose runs at an unreadable measure.

    Note the constraint must live on stMainBlockContainer: a max-width on a div we
    emit does nothing, because Streamlit renders its columns outside it. That is
    why the old .gate-wrap rule never worked.
    """
    assert "--fin-measure:" in CSS and "--fin-prose:" in CSS
    block = re.search(r'\[data-testid="stMainBlockContainer"\]\s*\{([^}]*)\}', CSS)
    assert block, "no container rule"
    body = block.group(1)
    assert "max-width: var(--fin-measure)" in body
    assert "margin-left: auto" in body and "margin-right: auto" in body


# --- self-hosted fonts --------------------------------------------------


def _font_faces():
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    return config["theme"]["fontFaces"]


def test_fonts_are_not_fetched_from_a_cdn():
    """A Google Fonts link would break offline mode and add a third-party request
    on first paint."""
    for face in _font_faces():
        assert "fonts.googleapis.com" not in face["url"]
        assert "fonts.gstatic.com" not in face["url"]
        assert face["url"].startswith("data:font/woff2;base64,"), face["family"]


def test_embedded_fonts_decode_to_real_woff2():
    """Catches a truncated or error-page payload, which would fall back silently."""
    import base64

    for face in _font_faces():
        raw = base64.b64decode(face["url"].split(",", 1)[1])
        assert raw[:4] == b"wOF2", f"{face['family']} is not valid woff2"
        assert len(raw) > 20_000, f"{face['family']} looks truncated"


def test_font_source_files_are_committed():
    """The data URIs are generated output; the woff2 files are the source of truth."""
    fonts = sorted((ROOT / "src" / "web_app" / "static" / "fonts").glob("*.woff2"))
    assert len(fonts) == 2, f"expected 2 variable fonts, found {[f.name for f in fonts]}"
    for f in fonts:
        assert f.read_bytes()[:4] == b"wOF2"


def test_serif_family_avoids_streamlit_collision():
    """Streamlit bundles a family called "Source Serif" and SILENTLY DROPS a
    declared fontFace whose name collides - the face never reaches document.fonts.

    Verified in the browser: declared as "Source Serif 4" it was absent entirely;
    renamed, it registers and loads. Hence the alias.
    """
    families = {f["family"] for f in _font_faces()}
    assert "Source Serif 4" not in families, "this name collides and gets dropped"
    assert "Fintor Serif" in families
    assert "Fintor Serif" in CSS, "the CSS must reference the aliased name"


# --- charts -------------------------------------------------------------


def test_views_never_build_a_figure_directly():
    """One factory, or the pages drift off the palette.

    A page that calls px./go.Figure itself loses the validated hues, the tabular
    axis labels, and the recessive grid - and reintroduces default Plotly blue.
    """
    import ast

    offenders = []
    for path in (ROOT / "src" / "web_app" / "views").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id in {"px", "go"}:
                    offenders.append(f"{path.name}:{node.lineno} {node.value.id}.{node.attr}")
    assert not offenders, "figures built outside charts.py: " + ", ".join(offenders)


def test_chart_palette_is_the_validated_order():
    """These exact hues passed scripts/validate_palette.js on Fintor's surfaces.

    Reordering changes which pairs are adjacent, which is what the CVD check
    measures - so the order is part of the validated artefact, not a preference.
    """
    from src.web_app.charts import SERIES_DARK, SERIES_LIGHT

    assert SERIES_LIGHT[:3] == ["#2a78d6", "#eb6834", "#1baf7a"]
    assert SERIES_DARK[:3] == ["#3987e5", "#d95926", "#199e70"]
    assert len(SERIES_LIGHT) == len(SERIES_DARK) == 8


def test_diverging_scale_has_a_neutral_midpoint():
    """Zero correlation must read as "nothing", not as a third category."""
    from src.web_app.charts import DIVERGING

    midpoint = [c for stop, c in DIVERGING if stop == 0.5][0]
    r, g, b = (int(midpoint[i:i + 2], 16) for i in (1, 3, 5))
    assert max(r, g, b) - min(r, g, b) < 12, f"{midpoint} is not neutral"


def test_charts_render_without_error():
    """Smoke: every factory function produces a figure from plausible data."""
    from src.web_app import charts

    dates = [f"d{i}" for i in range(60)]
    closes = [100 + i * 0.5 for i in range(60)]
    from src.core.market_calc import moving_average

    assert charts.allocation_bar({"equity": 60.0, "bond": 30.0, "cash": 10.0}).data
    assert charts.price_with_averages(dates, closes, moving_average(closes, 20),
                                      moving_average(closes, 50)).data
    assert charts.rebased_comparison(dates, {"A": closes, "B": closes}).data
    assert charts.projection_area([0, 1, 2], [100.0, 200.0, 300.0], 250.0).data
    assert charts.correlation_heatmap(["AAA", "BBB"], [[1.0, 0.4], [0.4, 1.0]]).data


def test_no_chart_paints_an_opaque_background():
    """Charts inherit the page surface; a white box would break dark mode."""
    from src.web_app import charts

    fig = charts.projection_area([0, 1], [1.0, 2.0], 1.5)
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.plot_bgcolor == "rgba(0,0,0,0)"


def test_allocation_uses_only_the_validated_four_hues():
    """scripts/validate_palette.js --pairs all: blue/orange/aqua/violet passes on
    #fbfaf7; every five-hue set tried FAILS the normal-vision floor (magenta vs
    orange at dE 12.9, below 15). That is a hard fail - direct labels do not
    excuse it - so the chart caps at four and folds the rest."""
    from src.web_app.charts import ALLOCATION_HUES, MAX_CLASSES, fold_to_max_classes

    assert ALLOCATION_HUES == ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]
    assert MAX_CLASSES == 4

    five = {"a": 40.0, "b": 25.0, "c": 20.0, "d": 10.0, "e": 5.0}
    folded = fold_to_max_classes(five)
    assert len(folded) == 4, "must never exceed the validated hue count"
    assert folded["other"] == 15.0, "the tail is summed, not dropped"
    assert sum(folded.values()) == sum(five.values()), "folding must conserve the total"


def test_other_is_neutral_not_a_fifth_hue():
    """"Other" is a bucket, not an identity; a categorical hue would make it
    read as a competing class."""
    from src.web_app.charts import ALLOCATION_HUES, OTHER_HUE, hue_for_class

    assert OTHER_HUE not in ALLOCATION_HUES
    assert hue_for_class("other") == OTHER_HUE
    r, g, b = (int(OTHER_HUE[i:i + 2], 16) for i in (1, 3, 5))
    assert max(r, g, b) - min(r, g, b) < 20, "the other bucket should be neutral"


def test_hue_follows_the_entity_not_its_rank():
    """Colour must identify the asset class, not its position in the sort.

    Assigning by rank means re-weighting a portfolio repaints the classes, and
    "the blue one" means something different on every persona.
    """
    from src.web_app.charts import hue_for_class

    assert hue_for_class("equity") != hue_for_class("bond")

    big = {"equity": 70.0, "bond": 30.0}
    small = {"equity": 20.0, "bond": 80.0}

    from src.web_app.charts import allocation_bar
    hues_big = {tr.name: tr.marker.color for tr in allocation_bar(big).data}
    hues_small = {tr.name: tr.marker.color for tr in allocation_bar(small).data}
    assert hues_big == hues_small, "re-weighting repainted the classes"


def test_unknown_asset_class_falls_back_to_the_neutral():
    from src.web_app.charts import OTHER_HUE, hue_for_class

    assert hue_for_class("something_new") == OTHER_HUE
