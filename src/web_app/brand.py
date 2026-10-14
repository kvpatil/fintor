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

# A mid-tone green. st.logo() takes a single image and cannot respond to the
# viewer's theme, so this has to hold contrast on both the light ground (#fbfaf7)
# and the dark one (#121714) - which rules out the theme-specific --accent values
# the rest of the app switches between.
MARK_GREEN = "#2f8f76"
WORDMARK_INK = "#17211d"

# Rectangles on a 32-unit grid: (x, y, w, h)
#
# A thin vertical axis with two detached bars beside it. The one-unit gap is what
# makes it read as a bar chart rather than only a letter: the axis stays light, the
# bars carry the weight. At favicon size that gap closes and the silhouette
# collapses to a clean F - which is the right degradation, not a loss.
AXIS = (6, 2, 2, 28)
BAR_UPPER = (9, 5, 17, 6)
BAR_LOWER = (9, 16, 11, 6)
MARK_RECTS = (AXIS, BAR_UPPER, BAR_LOWER)
GRID = 32


def _rects_svg(fill: str, dx: int = 0, dy: int = 0) -> str:
    return "".join(
        f'<rect x="{x + dx}" y="{y + dy}" width="{w}" height="{h}" fill="{fill}"/>'
        for x, y, w, h in MARK_RECTS
    )


def mark_svg(fill: str = MARK_GREEN) -> str:
    """Square, mark only. Used for st.logo(icon_image=...) and the collapsed slot."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}" '
        f'width="{GRID}" height="{GRID}" role="img" aria-label="Fintor">'
        f"{_rects_svg(fill)}</svg>"
    )


def logo_svg(fill: str = MARK_GREEN, ink: str = WORDMARK_INK) -> str:
    """Mark plus wordmark, for the expanded logo slot.

    Georgia matches the app's display face (.streamlit/config.toml sets font =
    "serif", and the type scale in theme.py is built on it).
    """
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 132 32" '
        'width="132" height="32" role="img" aria-label="Fintor">'
        f"{_rects_svg(fill)}"
        f'<text x="38" y="24" font-family="Georgia,\'Iowan Old Style\',serif" '
        f'font-size="21" font-weight="700" letter-spacing="-0.3" fill="{ink}">Fintor</text>'
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
            fill=MARK_GREEN,
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

    for name, content in (("fintor-mark.svg", mark_svg()), ("fintor-logo.svg", logo_svg())):
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
FAVICON_PATH = ASSETS / "fintor-favicon.png"


if __name__ == "__main__":
    for name, path in write_assets().items():
        print(f"{name:22s} {path.stat().st_size:>6d} bytes  {path}")
