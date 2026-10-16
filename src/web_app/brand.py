"""The Fintor mark: a leaf, split by its midrib.

The mark is one polygon, traced from the brand diagram. Geometry lives here once,
as a single point list, so the SVG and the PNG cannot drift apart - the SVG emits
the points and Pillow draws the same tuples.

It replaced a letter F built from candlestick bars. Worth knowing when reading
old commits: that mark encoded "finance" in its shape, where this one encodes
growth. The trade was made deliberately, for one brand across the app and its
architecture diagram rather than two.

Run `python -m src.web_app.brand` to regenerate the assets. They are committed, so
a fresh clone needs no build step.
"""

from __future__ import annotations

from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"

# A mid-tone violet. st.logo() takes a single image and cannot respond to the
# viewer's theme, so this has to hold contrast on BOTH grounds - which rules out
# the theme-specific --fin-accent values the rest of the app switches between.
# Measured: 4.89:1 on the light ground #f9f8fa, 3.60:1 on the dark one #131217.
#
# Named for its role, not its hue. It was MARK_INK, and when the brand moved
# to violet that name would have been actively misleading - the kind of lie a
# grep goes looking for and believes.
MARK_INK = "#7a52db"
# Light-mode ink, and the reason there are two logo files: an <img>-loaded SVG
# cannot inherit the page's colour, so the wordmark has to be baked per theme.
WORDMARK_INK = "#17211d"
WORDMARK_INK_DARK = "#e7ebe6"

# The leaf, as ONE polygon on a 32-unit grid.
#
# Traced from the brand diagram rather than drawn freehand: a row scan of the
# source PNG gave a 41x51 silhouette (aspect 0.804, so taller than wide) whose
# lower half is split by a diagonal midrib gap about two units across. The
# points below follow that scan clockwise from the tip.
#
# A single non-convex outline, not two shapes. The notch is cut up from the
# bottom - the outline runs down the right lobe, back up the inside of the gap,
# down the left lobe, and around the outer edge. Drawing it as two polygons
# would need the gap maintained in two places and they would drift.
#
# ONE point list, two renderers: mark_svg() emits it as <polygon points>, and
# favicon_png() hands the same tuples to ImageDraw.polygon. That is what keeps
# the SVG and the PNG from diverging now that the shape has curves - the old
# mark was rectangles-only for exactly this reason, and the invariant survives
# the change rather than being dropped with it.
LEAF = (
    (28, 0),                                      # tip, top right
    (30, 3), (30, 10), (29, 18), (26, 23),        # right edge, falling away
    (22, 27), (18, 29), (14, 31), (10, 32),       # foot of the right lobe
    (9, 30), (11, 24), (13, 20), (17, 15),        # up the notch, right side
    (16, 15), (12, 18), (8, 23), (6, 26),         # down the notch, left side
    (5, 29), (4, 32),                             # foot of the left lobe
    (2, 28), (0, 24), (0, 20), (2, 16),           # outer left edge, rising
    (3, 12), (6, 10), (10, 7), (15, 5),
    (20, 2), (24, 1),                             # back round to the tip
)
GRID = 32

# Wordmark layout. The mark now ends at x=27, so the text clears it at 36.
WORDMARK_X = 36
WORDMARK_SIZE = 25
WORDMARK_BOX = (150, 32)
# An <img>-loaded SVG is its own document: it cannot reach the page's @font-face,
# so the self-hosted Source Serif is unavailable here and the face resolves
# against whatever is installed. The stack is widened to keep the fallback in the
# same transitional-serif family rather than dropping to a default.
WORDMARK_STACK = (
    "Georgia,'Iowan Old Style','Source Serif 4','Source Serif Pro',"
    "'Charter','Times New Roman',serif"
)


def _leaf_svg(fill: str) -> str:
    points = " ".join(f"{x},{y}" for x, y in LEAF)
    return f'<polygon points="{points}" fill="{fill}"/>' 


def mark_svg(fill: str = MARK_INK) -> str:
    """Square, mark only. Used for st.logo(icon_image=...) and the collapsed slot."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}" '
        f'width="{GRID}" height="{GRID}" role="img" aria-label="Fintor">'
        f"{_leaf_svg(fill)}</svg>"
    )


def logo_svg(fill: str = MARK_INK, ink: str = WORDMARK_INK) -> str:
    """Mark plus wordmark - the lockup the header actually shows.

    A serif stack, to sit with the app's display face (`.streamlit/config.toml`
    sets `headingFont = "Fintor Serif, Georgia, serif"`; body is Inter Tight).
    It cannot BE Fintor Serif: see WORDMARK_STACK for why an <img> SVG has no
    access to the page's self-hosted woff2.
    """
    w, h = WORDMARK_BOX
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" role="img" aria-label="Fintor">'
        f"{_leaf_svg(fill)}"
        f'<text x="{WORDMARK_X}" y="25" font-family="{WORDMARK_STACK}" '
        f'font-size="{WORDMARK_SIZE}" font-weight="700" letter-spacing="-0.4" '
        f'fill="{ink}">Fintor</text>'
        "</svg>"
    )


def favicon_png(size: int = 64) -> bytes:
    """Draw the mark with Pillow at `size` px.

    st.set_page_config(page_icon=...) wants a raster path, and since the mark is
    pure rectangles this is an exact rendering rather than a rasterized guess.
    """
    from io import BytesIO

    from PIL import Image, ImageDraw

    scale = size / GRID
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).polygon(
        [(x * scale, y * scale) for x, y in LEAF], fill=MARK_INK)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def favicon_data_uri(size: int = 64) -> str:
    """The favicon as a `data:` URI.

    st.set_page_config(page_icon=...) routes file paths, PIL images, and raw bytes
    through Streamlit's media-file pipeline, which resolved to an empty string here
    - the icon was being silently dropped and the default Streamlit mark shown
    instead. A data URI needs no media manager, so it cannot be dropped. The whole
    icon is ~330 characters precisely because the mark is three rectangles.
    """
    import base64

    return "data:image/png;base64," + base64.b64encode(favicon_png(size)).decode("ascii")


def write_assets(target: Path | None = None) -> dict[str, Path]:
    out = target or ASSETS
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    for name, content in (
        ("fintor-mark.svg", mark_svg()),
        ("fintor-logo.svg", logo_svg()),
        # The dark wordmark is a separate file because an <img> cannot be
        # recoloured by CSS; app.py picks one with theme.is_dark().
        ("fintor-logo-dark.svg", logo_svg(ink=WORDMARK_INK_DARK)),
    ):
        path = out / name
        path.write_text(content, encoding="utf-8")
        written[name] = path

    icon = out / "fintor-favicon.png"
    icon.write_bytes(favicon_png())
    written["fintor-favicon.png"] = icon
    return written


# Paths the app reads. Resolved here so no caller hardcodes a filename.
MARK_PATH = ASSETS / "fintor-mark.svg"
LOGO_PATH = ASSETS / "fintor-logo.svg"
LOGO_DARK_PATH = ASSETS / "fintor-logo-dark.svg"
FAVICON_PATH = ASSETS / "fintor-favicon.png"


if __name__ == "__main__":
    for name, path in write_assets().items():
        print(f"{name:22s} {path.stat().st_size:>6d} bytes  {path}")
