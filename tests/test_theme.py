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

    `em` counts, not just `rem`. This checked only `rem` for a long time, and
    two `code` rules sat at 0.86em and 0.82em - about 13.8px and 13.1px - in
    plain sight the whole time, because the unit was the one the guard did not
    read. An em value is relative to its parent rather than the root, so the
    multiplier here assumes a 16px parent; that is right for both offenders it
    caught and conservative everywhere else, since a smaller parent only makes
    the real size smaller.
    """
    offenders = [
        (match, float(re.search(r"[0-9.]+", match).group(0)) * 16)
        for match in re.findall(r"font-size:\s*[0-9.]+r?em", CSS)
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
    ".chip", ".fin-chip", ".gate-ask", ".signin-account-nums",
    ".signin-account-head-line", ".signin-help", ".signin-pillar",
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


def test_gate_paragraph_top_margins_outrank_streamlit():
    """A top margin on a bare `.gate-*` class never reaches the element.

    Streamlit styles `[data-testid="stMarkdownContainer"] p` - specificity
    (0,1,1) - which beats a plain class at (0,1,0). The symptom is silent:
    `margin-bottom` comes through, `margin-top` computes to 0, and the page
    just looks wrong with no error anywhere. It cost two spacing fixes that
    appeared to land and did nothing - the 30px above "Demo accounts" and the
    18px meant to keep the disclaimer rule off the cards, which ended up drawn
    exactly on the card edge at a measured 0.0px gap.

    Note it is NOT margin collapsing, which was the first diagnosis. A
    collapsed margin still reports its declared value; 0px means overridden.

    So: any gate paragraph rule that sets a non-zero top margin must carry the
    container in its selector.
    """
    offenders = []
    # Comments first: a /* ... */ before a rule otherwise lands inside the
    # selector group and turns a real finding into an unreadable one.
    css = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    for match in re.finditer(r"(^|\})\s*([^{}@]*?\.gate-[\w-]+)\s*\{([^}]*)\}", css):
        selector, body = match.group(2).strip(), match.group(3)

        top = re.search(r"margin-top:\s*([^;]+);", body)
        if not top:
            shorthand = re.search(r"margin:\s*([^;]+);", body)
            if not shorthand:
                continue
            first = shorthand.group(1).split()[0]
            top_value = first
        else:
            top_value = top.group(1)
        if top_value.strip() in {"0", "0px", "auto"}:
            continue
        if "stMarkdownContainer" not in selector:
            offenders.append(f"{selector} sets margin-top:{top_value.strip()}")

    assert not offenders, (
        "these top margins will be overridden to 0 by Streamlit; qualify the "
        "selector with [data-testid=\"stMarkdownContainer\"]: " + "; ".join(offenders))


# --- both themes --------------------------------------------------------


THEME_TOKENS = ("--fin-ink", "--fin-muted", "--fin-line", "--fin-accent",
                "--fin-warn", "--fin-paper", "--fin-field-line")


@pytest.mark.parametrize("token", THEME_TOKENS)
def test_every_colour_token_is_redefined_for_dark(token):
    """A token that only exists in :root survives into dark mode unchanged.

    That is exactly how near-black --fin-ink and near-white --fin-paper ended up on
    a dark ground: they were styled through, but never overridden.
    """
    from src.web_app.theme import DARK_TOKENS

    assert token in DARK_TOKENS, f"{token} is not redefined for dark"


def test_the_os_preference_is_not_the_theme_signal():
    """Measured in the browser, OS on light and Streamlit set to Dark:

        bodyBg      rgb(18, 23, 20)     <- dark, from Streamlit
        --fin-paper #fffefb             <- light, the media query was false
        valueColor  rgb(231, 235, 230)  <- light, from Streamlit

    A near-white card under light text, 1.2:1. `prefers-color-scheme` follows
    the OPERATING SYSTEM, and Streamlit's own toggle can disagree with it in
    both directions, so it is simply the wrong question to ask.
    """
    assert "prefers-color-scheme" not in CSS


def test_both_themes_are_attribute_scoped_so_either_can_win():
    """Whichever way the toggle moves, the selected block must outrank the
    plain `:root` defaults - including the dark block the server emits for the
    first paint. Specificity does that only if BOTH are attribute-scoped."""
    for mode in ("dark", "light"):
        assert f':root[data-theme="{mode}"]' in CSS, f"no {mode} block"
    for token in THEME_TOKENS:
        light = re.search(r':root\[data-theme="light"\]\s*\{([^}]*)\}', CSS)
        assert token in light.group(1), f"{token} missing from the light block"


def test_a_probe_keeps_the_attribute_in_step_with_what_streamlit_painted():
    """Streamlit's theme menu repaints WITHOUT rerunning the script, so a
    server-side decision goes stale the moment the user toggles - verified by
    switching Dark -> Light and watching black cards survive on a light page.

    Streamlit stamps no theme attribute and defines no CSS variables, so the
    only always-current signal is the colour it paints on stApp. The probe
    reads that and sets the attribute itself.
    """
    from src.web_app.theme import THEME_PROBE, inject
    import inspect

    assert 'data-testid="stApp"' in THEME_PROBE, "the probe must read what was painted"
    assert "setAttribute('data-theme'" in THEME_PROBE
    assert "MutationObserver" in THEME_PROBE, "a one-shot read cannot track a toggle"
    assert "theme_probe()" in inspect.getsource(inject)


def test_inject_emits_the_dark_block_only_in_dark_mode(monkeypatch):
    from src.web_app import theme

    emitted = []
    monkeypatch.setattr(theme.st, "markdown", lambda css, **_kw: emitted.append(css))

    monkeypatch.setattr(theme, "is_dark", lambda: False)
    theme.inject()
    assert theme.DARK_CSS not in emitted

    emitted.clear()
    monkeypatch.setattr(theme, "is_dark", lambda: True)
    theme.inject()
    assert theme.DARK_CSS in emitted


def test_is_dark_never_raises_without_a_script_context():
    """Called from tests and from the fonts generator, where st.context is absent."""
    from src.web_app.theme import is_dark

    assert is_dark() is False


def test_config_does_not_pin_a_single_palette():
    """`base` pins the app to one palette and ignores the viewer entirely."""
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    theme = config.get("theme", {})
    assert "base" not in theme, "theme.base pins the palette; use [theme.light]/[theme.dark]"
    assert "light" in theme and "dark" in theme, "both palettes must be declared"
    assert theme["light"]["backgroundColor"] != theme["dark"]["backgroundColor"]


def test_text_fields_have_a_visible_edge_in_both_themes():
    """Streamlit borders a text field in the same colour as its own fill, and in
    dark mode that fill equals the card behind it - measured rgb(29,27,33) on
    rgb(29,27,33), so the Username and Password boxes were simply not there.

    --fin-line is NOT an acceptable fix and the point of this test is to stop
    someone reaching for it: against a field fill it is 1.23:1 light and 1.29:1
    dark, where WCAG 1.4.11 asks 3:1 of a control boundary. The dedicated token
    clears that on both the fill and the card.
    """
    rule = re.search(r'\[data-testid="stTextInputRootElement"\][^{]*\{([^}]*)\}', CSS)
    assert rule, "no rule gives a text field a border"
    assert "var(--fin-field-line)" in rule.group(1), (
        "the field border must come from the dedicated token, not --fin-line")

    for mode, fill, card in (("light", "#eeedf1", "#fdfdfd"),
                             ("dark", "#221f28", "#1d1b21")):
        block = re.search(rf':root\[data-theme="{mode}"\]\s*\{{([^}}]*)\}}', CSS)
        line = re.search(r"--fin-field-line:\s*(#[0-9a-fA-F]{6})", block.group(1))
        assert line, f"--fin-field-line missing from the {mode} block"
        for ground, label in ((fill, "fill"), (card, "card")):
            ratio = _contrast(line.group(1), ground)
            assert ratio >= 3.0, (
                f"{mode} field border is {ratio:.2f}:1 on the {label} - "
                "under the 3:1 WCAG asks of a control boundary")


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


def _token(source: str, token: str) -> str:
    """First hex value for `token` in a CSS fragment (the light :root, or DARK_TOKENS)."""
    found = re.search(rf"{token}:\s*(#[0-9a-fA-F]{{6}})", source)
    assert found, f"{token} not found"
    return found.group(1)


def _light_root() -> str:
    block = re.search(r":root \{(.*?)\n\}", CSS, re.S)
    assert block, "no :root block"
    return block.group(1)


def test_muted_contrast_passes_aa_on_both_grounds():
    """Darkening the light grey is the kind of change that quietly breaks dark mode,
    so both directions are measured rather than one assumed."""
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))

    light_muted = _token(_light_root(), "--fin-muted")
    light_bg = config["theme"]["light"]["backgroundColor"]
    light_ratio = _contrast(light_muted, light_bg)

    from src.web_app.theme import DARK_TOKENS

    dark_muted = _token(DARK_TOKENS, "--fin-muted")
    dark_bg = config["theme"]["dark"]["backgroundColor"]
    dark_ratio = _contrast(dark_muted, dark_bg)

    assert light_ratio >= 4.5, f"light muted {light_muted} on {light_bg} is {light_ratio:.2f}:1"
    assert dark_ratio >= 4.5, f"dark muted {dark_muted} on {dark_bg} is {dark_ratio:.2f}:1"


def test_accent_is_legible_on_its_own_ground():
    """The accent carries the eyebrows and the active breadcrumb, so it is text."""
    from src.web_app.theme import DARK_TOKENS

    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    light = _contrast(_token(_light_root(), "--fin-accent"),
                      config["theme"]["light"]["backgroundColor"])
    dark = _contrast(_token(DARK_TOKENS, "--fin-accent"),
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
    from src.web_app.theme import DARK_TOKENS

    for token in ("--tab-workspace", "--tab-reference", "--dot-live",
                  "--dot-cached", "--dot-attention"):
        assert f"{token}:" in CSS, f"{token} undefined"
        assert token in DARK_TOKENS, f"{token} not redefined for dark"


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


def test_allocation_caps_at_the_validated_hue_count():
    """scripts/validate_palette.js --pairs all: blue/orange/aqua/magenta passes
    on #f9f8fa; every five-hue set tried FAILS the normal-vision floor (dE 12.9,
    below 15). That is a hard fail - direct labels do not excuse it - so the
    chart caps at four and folds the rest.

    The hues themselves are NOT asserted as a literal list here. Slot 4 moved
    once already when the brand turned violet, and a test that pins the exact
    hex just has to be edited to match whatever the code now says, which proves
    nothing. The properties that matter are checked instead: how many, that they
    are distinct, and (below) that none of them impersonates the brand.
    """
    from src.web_app.charts import ALLOCATION_HUES, MAX_CLASSES, fold_to_max_classes

    assert MAX_CLASSES == 4
    assert len(ALLOCATION_HUES) == MAX_CLASSES
    assert len(set(ALLOCATION_HUES)) == MAX_CLASSES, "a hue is repeated"

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


def test_no_metric_value_contains_two_dollar_signs():
    """Streamlit renders a value with two "$" as LaTeX.

    "$189.80 - $239.24" came out as green maths instead of a range. Currency
    belongs in the label when a value needs two of them.
    """
    import re as _re

    src = (ROOT / "src" / "web_app" / "views" / "workspace.py").read_text(encoding="utf-8")
    for call in _re.findall(r"\.metric\(([^\n]*)\)", src):
        value = call.split(",", 1)[1] if "," in call else ""
        assert value.count("$") < 2, f"two dollar signs will render as LaTeX: {call.strip()}"


# --- heatmap cell labels must be readable on their own fill ---------------


def _relative_luminance(hex_colour: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a: str, b: str) -> float:
    lo, hi = sorted((_relative_luminance(a), _relative_luminance(b)))
    return (hi + 0.05) / (lo + 0.05)


def _sample_ramp(ramp, t: float) -> str:
    """Colour at position t in a Plotly colorscale, by linear interpolation."""
    for (p0, c0), (p1, c1) in zip(ramp, ramp[1:], strict=False):
        if p0 <= t <= p1:
            k = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            return "#" + "".join(
                f"{round(int(c0[i:i + 2], 16) + (int(c1[i:i + 2], 16) - int(c0[i:i + 2], 16)) * k):02x}"
                for i in (1, 3, 5))
    raise AssertionError(f"t={t} outside the ramp")


@pytest.mark.parametrize("dark", [False, True])
def test_every_correlation_cell_label_clears_wcag_aa(dark):
    """The cell value is drawn ON the fill, so the fill is its background.

    This is the bug that shipped: the text colour flipped to white above
    |r| 0.55, a threshold that was guessed. At r=0.57 the fill was #7fabdf,
    where white scores 2.39:1. Sampling the whole ramp is the only honest
    version of this check - a single spot value would have passed too.
    """
    from src.web_app.charts import scheme

    sc = scheme(dark)
    worst = min(
        (_contrast(_sample_ramp(sc.diverging, i / 40), sc.ink), i / 40)
        for i in range(41)
    )
    assert worst[0] >= 4.5, (
        f"{'dark' if dark else 'light'}: label {sc.ink} on "
        f"{_sample_ramp(sc.diverging, worst[1])} is {worst[0]:.2f}:1")


def test_the_diverging_midpoint_is_neutral():
    """A hue at the midpoint would make "uncorrelated" look like a category."""
    from src.web_app.charts import DIVERGING, DIVERGING_DARK

    for ramp in (DIVERGING, DIVERGING_DARK):
        mid = ramp[1][1]
        r, g, b = (int(mid[i:i + 2], 16) for i in (1, 3, 5))
        assert max(r, g, b) - min(r, g, b) <= 12, f"{mid} is not neutral"


# --- reference lines are not series ---------------------------------------


def test_the_goal_target_line_is_not_a_categorical_hue():
    """It was SERIES_LIGHT[1] - orange, which is "bond" on the Portfolio page
    and reads as a warning. A target is a rule, not a second series."""
    from src.web_app.charts import SERIES_DARK, SERIES_LIGHT, projection_area

    for dark in (False, True):
        fig = projection_area([1, 2, 3], [10.0, 20.0, 30.0], 25.0, dark=dark)
        line = fig.layout.shapes[0].line.color
        assert line not in SERIES_LIGHT and line not in SERIES_DARK


# --- dark mode is wired, not merely defined -------------------------------


def test_the_schemes_actually_differ_in_a_built_figure():
    """SERIES_DARK existed for a while as a constant no figure ever read."""
    from src.web_app.charts import price_with_averages

    light = price_with_averages(["a", "b"], [1.0, 2.0], [None, 1.5], [None, None])
    dark = price_with_averages(["a", "b"], [1.0, 2.0], [None, 1.5], [None, None],
                               dark=True)
    assert light.data[2].line.color != dark.data[2].line.color
    assert light.layout.font.color != dark.layout.font.color


def test_views_ask_for_the_theme_rather_than_assuming_light():
    """A Plotly figure cannot inherit the page theme the way CSS can."""
    src = (ROOT / "src" / "web_app" / "views" / "workspace.py").read_text(encoding="utf-8")
    assert "is_dark()" in src
    for call in ("allocation_bar", "correlation_heatmap", "price_with_averages",
                 "rebased_comparison", "projection_area"):
        start = src.index(f"charts.{call}(")
        assert "dark=" in src[start:start + 400], f"{call} is built without a scheme"


# --- machine names never reach the screen ---------------------------------


def test_asset_class_labels_are_human():
    from src.web_app.labels import asset_class

    assert asset_class("single_stock") == "Single stock"
    assert asset_class("reit") == "REITs"
    assert "_" not in asset_class("single_stock")


def test_an_unknown_asset_class_still_reads_as_words():
    from src.web_app.labels import asset_class

    assert asset_class("private_credit") == "Private credit"


def test_no_dataframe_column_key_is_a_machine_name():
    """`single_stock` was a cell value and `assumed_return_pct` a column header.

    A reader who sees an underscore knows they are looking at a database dump.
    """
    import ast

    src = (ROOT / "src" / "web_app" / "views" / "workspace.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key in node.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                assert "_" not in key.value, (
                    f"{key.value!r} reads as a field name, not a column header")


@pytest.mark.parametrize("view", ["workspace.py", "internals.py", "chat.py", "about.py"])
def test_every_table_configures_its_columns(view):
    """The Goals table had no literal keys at ALL - it handed `proj["scenarios"]`
    straight to st.dataframe, so quant.py's field names became the headers and
    a bool became a checkbox that looked clickable.

    Parametrised over EVERY view, not just the one that had the bug. Guarding
    only workspace.py left the identical defect sitting in internals.py for
    another three commits, because the test was written against the page
    instead of against the pattern.

    Requiring column_config is what catches that shape: it is impossible to
    pass a domain dict straight through and still satisfy this.
    """
    import ast

    path = ROOT / "src" / "web_app" / "views" / view
    if not path.exists():
        pytest.skip(f"{view} does not exist")
    for call in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "dataframe"):
            kwargs = {kw.arg for kw in call.keywords}
            assert "column_config" in kwargs, (
                f"{view}:{call.lineno} ships raw field names as headers")


def test_no_view_prints_a_python_container_into_the_page():
    """"Per-persona spend: {'unassigned': 0.0}" was on screen. An f-string that
    interpolates a dict renders its repr, braces and quotes included."""
    import ast

    offenders = []
    for path in (ROOT / "src" / "web_app" / "views").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.JoinedStr):
                continue
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    rendered = ast.unparse(part.value)
                    if any(h in rendered for h in
                           ("by_persona()", "['signals']", '["signals"]')):
                        offenders.append(f"{path.name}:{node.lineno} -> {rendered}")
    assert not offenders, "rendered as a repr: " + "; ".join(offenders)


# --- cards and the rail -------------------------------------------------


def test_cards_style_through_tokens_so_they_survive_dark_mode():
    """A hardcoded #fffefb card ground is exactly the bug that shipped before."""
    block = re.search(r'\[class\*="st-key-card-"\] \{([^}]*)\}', CSS)
    assert block, "no card rule"
    body = block.group(1)
    assert "var(--fin-paper)" in body, "card ground must be a token"
    assert "var(--fin-line)" in body, "card border must be a token"
    assert not re.search(r"#[0-9a-fA-F]{6}", body), f"literal colour in card rule: {body}"


def test_the_card_hook_is_a_key_class_not_a_streamlit_testid():
    """st.container(key=...) emits st-key-*, which is a documented contract.
    A data-testid is an implementation detail that moves between versions."""
    assert 'st-key-card-' in CSS
    assert 'data-testid="stVerticalBlockBorderWrapper"' not in CSS


def test_the_probe_container_is_out_of_flow_but_not_hidden():
    """A zero-height iframe still eats one 16px flex gap, which pushed every
    page down. display:none would fix the gap but a browser may then never load
    the iframe, and an unloaded probe means no theme switching at all.
    """
    block = re.search(r"\.st-key-theme-probe \{([^}]*)\}", CSS)
    assert block, "the probe container is not styled"
    body = block.group(1)
    assert "position: absolute" in body
    assert "display: none" not in body, "a hidden iframe may never run"


@pytest.mark.parametrize("token", ["--fin-note-ground", "--fin-up", "--fin-down"])
def test_card_era_tokens_exist_in_both_themes(token):
    from src.web_app.theme import DARK_TOKENS

    assert token in _light_root(), f"{token} missing from the light root"
    assert token in DARK_TOKENS, f"{token} missing from dark"


@pytest.mark.parametrize("name,ground", [
    ("--fin-up", "light"), ("--fin-down", "light"),
    ("--fin-up", "dark"), ("--fin-down", "dark"),
])
def test_direction_colours_are_legible_on_their_card(name, ground):
    """These sit on the CARD, not the page, so the card is the background."""
    from src.web_app.theme import DARK_TOKENS

    source = DARK_TOKENS if ground == "dark" else _light_root()
    ratio = _contrast(_token(source, name), _token(source, "--fin-paper"))
    assert ratio >= 4.5, f"{name} on the {ground} card is {ratio:.2f}:1"


# --- the active tab, and the gate action bar, are the same problem ---------


@pytest.mark.parametrize("ground", ["light", "dark"])
def test_accent_surfaces_carry_a_legible_label(ground):
    """Both the active nav tab and the gate action bar are paper-on-accent.

    Measured on the active tab BEFORE the fix: rgb(23,33,29) on rgb(31,111,92),
    2.74:1. The colour was never wrong - theme.py already said
    `color: var(--fin-paper)` on the link - it just never reached the label.
    """
    from src.web_app.theme import DARK_TOKENS

    source = DARK_TOKENS if ground == "dark" else _light_root()
    ratio = _contrast(_token(source, "--fin-accent"), _token(source, "--fin-paper"))
    assert ratio >= 4.5, f"{ground}: paper on accent is {ratio:.2f}:1"


def test_the_active_nav_label_has_its_own_rule():
    """Streamlit puts the label in a <p> inside stMarkdownContainer and colours
    that element directly. A direct declaration on a child beats an inherited
    one, !important or not - so the parent rule alone did nothing, which is
    exactly why the icon already had a descendant rule and the text did not.
    """
    active = r'\[data-testid="stTopNavLink"\]\[aria-current="page"\]'
    assert re.search(active + r'\s+\[data-testid="stMarkdownContainer"\]', CSS), \
        "the active label has no descendant rule; the colour will not reach it"


def test_the_sign_in_button_colours_its_own_label():
    """Streamlit styles the inner <p> of a button directly, so colour and weight
    set on the button element alone never reach the text. The active nav tab
    sat at 2.74:1 for exactly this reason."""
    block = re.search(
        r"\.st-key-signin-card \[data-testid=\"stFormSubmitButton\"\] > button p,?"
        r"[^{]*\{([^}]*)\}", CSS)
    assert block, "no rule targets the sign-in button label"
    assert "var(--fin-paper)" in block.group(1)
    assert "font-weight" in block.group(1), "weight inherits no better than colour"


def test_no_dead_selector_for_the_about_section():
    """Measured: the collapsed stTopNavSection exposes no aria-current while one
    of its pages is open, so a :has([aria-current]) rule can never match. Dead
    CSS reads as a working feature - this is the data-theme lesson again."""
    assert 'stTopNavSection"]:has(' not in CSS


# --- the gate ------------------------------------------------------------


def test_the_disclaimer_is_not_held_to_a_narrow_measure():
    """It spans the full account grid above it. At 72ch it wrapped at 666px
    inside a 960px row, and that ragged edge is what read as unfinished.

    NO cap now passes, and is the strongest form of this guarantee - the
    container is already the grid's width, so any ch cap could only make the
    paragraph narrower than the cards it sits under. An earlier version of this
    test REQUIRED a cap of >=90ch and so would have failed the correct fix.
    A cap is still allowed, but only a generous one.

    The brand subline is not checked here; it is uncapped for the same reason.
    """
    rule = re.search(r"\.gate-foot\s*\{([^}]*)\}", CSS)
    assert rule, "no rule for .gate-foot"
    found = re.search(r"max-width:\s*(\d+)ch", rule.group(1))
    assert found is None or int(found.group(1)) >= 90, (
        f".gate-foot is capped at {found.group(1)}ch")


def test_the_pages_are_wide_and_the_READING_is_what_is_capped():
    """One measure for every page, with running text capped per element.

    This replaces an assertion that the gate was WIDER than the app pages.
    That held while --fin-measure was 1120px, justified as a reading width -
    but it also meant every dashboard page threw away 320px either side on a
    1600px screen, 960px of usable content out of 1600, while the login
    screen used 32px. The reading-width constraint was being applied to the
    page when it belongs to the paragraph.

    So the invariant inverted: the page is now as wide as the viewport
    sensibly allows, and the things that are actually READ carry the cap. If
    someone widens the measure again without those caps, long-form answers
    stretch to 1500px and this fails.
    """
    from src.web_app.gate import GATE_CHROME_CSS

    measure = re.search(r"--fin-measure:([^;]+);", CSS)
    assert measure, "--fin-measure is not declared"
    assert "vw" in measure.group(1), (
        "the measure has no viewport term, so a narrow screen loses its margin")
    cap = int(re.search(r"(\d+)px", measure.group(1)).group(1))
    assert cap >= 1500, f"the page cap is {cap}px; that is the old narrow measure"

    # The gate uses the same value rather than a wider one of its own.
    gate = re.search(r"--fin-measure-gate:([^;]+);", CSS)
    assert gate and "--fin-measure" in gate.group(1), (
        "the gate has drifted back to a separate measure")
    assert "--fin-measure-gate" in GATE_CHROME_CSS, "the gate never applies it"

    # And the caps that make the width safe.
    assert re.search(r"\.fin-prose p, \.fin-prose li \{[^}]*max-width", CSS), (
        "reference prose is uncapped")
    chat = re.search(
        r'\[data-testid="stChatMessage"\][^{]*\{([^}]*)\}', CSS)
    assert chat and "max-width" in chat.group(1), (
        "the chat transcript is uncapped; answers will stretch to the full page")


def test_the_page_inset_is_declared_not_inherited():
    """Streamlit's default is 5rem, which was most of the whitespace. It is
    set explicitly so the number is visible and tunable in one place."""
    block = re.search(r'\[data-testid="stMainBlockContainer"\][^{]*\{([^}]*)\}', CSS)
    assert block, "no stMainBlockContainer override"
    body = block.group(1)
    assert "padding-left: var(--fin-pad)" in body
    assert "padding-right: var(--fin-pad)" in body


def test_the_sign_in_card_is_a_keyed_container():
    """A wrapper div would not work: Streamlit renders its elements outside any
    HTML we emit, which is why the old .gate-wrap constrained nothing for weeks.
    st.container(key=...) emits a st-key-* class, which is a real hook."""
    block = re.search(r"\.st-key-signin-card \{([^}]*)\}", CSS)
    assert block, "no sign-in card rule"
    assert "var(--fin-line)" in block.group(1)
    assert "var(--fin-paper)" in block.group(1)


def test_no_octal_artefact_survives_into_the_css():
    """`content: "\\2192"` in a plain Python triple-quoted string is read as
    OCTAL before CSS sees it, and a button once rendered the literal text 92.
    Kept as a general guard now that the arrow itself is gone."""
    for code in range(1, 32):
        assert chr(code) not in CSS.replace("\n", ""), \
            f"control character {code} in CSS - probably a mangled escape"


# --- the brand must not be mistakable for data ---------------------------


def _hue_degrees(hex_colour: str) -> float:
    import colorsys

    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def _hue_distance(a: str, b: str) -> float:
    d = abs(_hue_degrees(a) - _hue_degrees(b))
    return min(d, 360 - d)


@pytest.mark.parametrize("ground", ["light", "dark"])
def test_no_categorical_hue_impersonates_the_brand(ground):
    """Slot 4 was violet #4a3aa7 when the brand turned violet - 8.8 degrees
    apart, so "single stock" in the allocation bar was painted almost exactly
    the accent. A category wearing the brand colour reads as emphasis rather
    than as a category.

    A standing guard, not a one-off fix: the next brand change has to notice.
    """
    from src.web_app.charts import SERIES_DARK, SERIES_LIGHT
    from src.web_app.theme import DARK_TOKENS

    source = DARK_TOKENS if ground == "dark" else _light_root()
    accent = _token(source, "--fin-accent")
    series = SERIES_DARK if ground == "dark" else SERIES_LIGHT
    for hue in series:
        distance = _hue_distance(hue, accent)
        assert distance >= 30, (
            f"{ground}: series hue {hue} is {distance:.1f} deg from the accent "
            f"{accent}; it will read as the brand")


def test_the_mark_reads_on_both_grounds():
    """st.logo takes ONE image and cannot respond to the theme, which is why
    the mark is a mid-tone rather than either --fin-accent value."""
    import tomllib

    from src.web_app.brand import MARK_INK

    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    for mode in ("light", "dark"):
        ground = config["theme"][mode]["backgroundColor"]
        ratio = _contrast(MARK_INK, ground)
        assert ratio >= 3.0, f"the mark is {ratio:.2f}:1 on the {mode} ground"


def test_no_colour_token_is_named_for_a_colour_it_is_not():
    """`MARK_GREEN = "#7a52db"` would be a lie a grep goes looking for and
    believes. Names say role, or they say the truth."""
    import re as _re

    from src.web_app import brand, charts

    for module in (brand, charts):
        src = (ROOT / "src" / "web_app" / f"{module.__name__.split('.')[-1]}.py")
        for name, value in _re.findall(r'^([A-Z][A-Z_0-9]*)\s*=\s*"(#[0-9a-fA-F]{6})"',
                                       src.read_text(encoding="utf-8"), _re.M):
            hue = _hue_degrees(value)
            for word, lo, hi in (("GREEN", 75, 170), ("BLUE", 185, 265),
                                 ("RED", 345, 15), ("VIOLET", 255, 295)):
                if word not in name:
                    continue
                ok = (lo <= hue <= hi) if lo < hi else (hue >= lo or hue <= hi)
                assert ok, f"{name} = {value} is at hue {hue:.0f}, not {word.lower()}"


def test_the_status_dots_did_not_follow_the_brand():
    """Live/cached/attention are MEANING, not brand. When the brand was green
    the live dot was the same green; the violet move must not have dragged it
    along, because then "live" would just mean "Fintor"."""
    from src.web_app.theme import DARK_TOKENS

    for source, mode in ((_light_root(), "light"), (DARK_TOKENS, "dark")):
        accent = _token(source, "--fin-accent")
        live = _token(source, "--dot-live")
        assert live != accent, f"{mode}: the live dot is the brand colour"
        assert _hue_distance(live, accent) >= 30, (
            f"{mode}: the live dot {live} is too close to the accent {accent}")
        # It should still be the same green the app uses for "up".
        assert live == _token(source, "--fin-up"), (
            f"{mode}: one app, one green that means good")


def test_the_live_chip_and_the_live_dot_agree():
    """Both say "the data is live". When the brand was green they happened to
    be the same colour; after the violet move the chip stayed on --fin-accent
    and the dot on the state green, so one screen showed two colours for one
    meaning."""
    from src.web_app.components import STATUS_LABEL

    assert STATUS_LABEL["live"][1] == "good", "the live chip is back on the brand"
    rule = re.search(r"\.fin-chip-good \{([^}]*)\}", CSS)
    assert rule, "no good-state chip rule"
    assert "var(--dot-live)" in rule.group(1), "the chip must reuse the state green"
