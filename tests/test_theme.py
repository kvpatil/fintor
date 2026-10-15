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
