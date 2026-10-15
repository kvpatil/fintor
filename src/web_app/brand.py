"""The Fintor mark: a letter F built from a candlestick chart.

The mark is rectangles only - a wick and two price bars. That is deliberate twice
over: it stays crisp at 16px where curves would mush, and it means Pillow can draw
the favicon exactly rather than approximating a rendered SVG. Geometry lives here
once so the SVG and the PNG cannot drift apart.

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

# Rectangles on a 32-unit grid: (x, y, w, h)
#
# A vertical axis with two detached bars beside it. The gap is what makes it read
# as a bar chart rather than only a letter: at favicon size it closes and the
# silhouette collapses to a clean F, which is the right degradation, not a loss.
#
# Weights doubled from the original 2u axis / 6u bars. At the 24px the header
# actually renders, three hairlines read as a smudge - the mark needs mass to
# survive at the size it is used, and the open, transparent character is kept by
# widening the gap to 2u rather than by filling a badge behind it.
AXIS = (5, 2, 4, 28)
BAR_UPPER = (11, 4, 16, 8)
BAR_LOWER = (11, 16, 11, 8)
MARK_RECTS = (AXIS, BAR_UPPER, BAR_LOWER)
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


def _rects_svg(fill: str, dx: int = 0, dy: int = 0) -> str:
    return "".join(
        f'<rect x="{x + dx}" y="{y + dy}" width="{w}" height="{h}" fill="{fill}"/>'
        for x, y, w, h in MARK_RECTS
    )


def mark_svg(fill: str = MARK_INK) -> str:
    """Square, mark only. Used for st.logo(icon_image=...) and the collapsed slot."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}" '
        f'width="{GRID}" height="{GRID}" role="img" aria-label="Fintor">'
        f"{_rects_svg(fill)}</svg>"
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
        f"{_rects_svg(fill)}"
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
    draw = ImageDraw.Draw(img)
    for x, y, w, h in MARK_RECTS:
        draw.rectangle(
            [round(x * scale), round(y * scale),
             round((x + w) * scale) - 1, round((y + h) * scale) - 1],
            fill=MARK_INK,
        )
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
