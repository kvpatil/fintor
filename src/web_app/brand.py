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
# The stem, and the tagline under the wordmark - deliberately the same value,
# so the lockup and the line beneath it read as one thing. A LIGHTER violet, as
# asked, and the lightest one that still works: it is fixed ink in a themeless
# <img>, so it has to hold on both grounds, and measured it gives 3.11:1 on the
# light ground and 5.66:1 on the dark. That clears AA for LARGE text only - the
# tagline is 1.9rem/700, well past the 18.66px bold threshold. Do not reuse
# this for body copy, where 3.11:1 is a fail.
MARK_RIB = "#9b7aeb"
# Light-mode ink, and the reason there are two logo files: an <img>-loaded SVG
# cannot inherit the page's colour, so the wordmark has to be baked per theme.
WORDMARK_INK = "#17211d"
WORDMARK_INK_DARK = "#e7ebe6"

# The leaf: a body and a stem, each ONE cubic-Bezier outline on a 32-unit grid.
#
# It was a 30-point polygon traced off the brand diagram, and it read as a
# blob - a leaf is two smooth arcs meeting at a point, and a row-scan of a PNG
# cannot give you that. With curves the tip falls out of the two tangents
# meeting, where the polygon had to fake it with short segments.
#
# The axis runs bottom-left (base) to top-right (tip) at 45 degrees. Each side
# of the body is one cubic bulging away from that axis.
#
# The midrib used to be a SLIT - a wedge of negative space cut up from the
# base. It is now a drawn shape in MARK_RIB, so the stem carries colour
# instead of showing the page through, and it extends past the base so the
# leaf reads as picked rather than floating. Two shapes, not one, because a
# single path cannot hold two fills.
BASE = (5.0, 27.0)
TIP = (27.0, 5.0)
# Both controls near the tip sit close to the axis, which is what sharpens it:
# the first draft put them far off-axis, the tangents met at a wide angle and
# the tip came out blunt. Rendered at 11x against two alternatives before
# picking this one - a slenderer version read as a willow leaf and lost its
# body at the 24px nav size.
LEAF_BODY = (
    ("M", BASE),
    ("C", (2.8, 14.6), (14.6, 7.2), TIP),
    ("C", (24.6, 17.4), (17.4, 29.2), BASE),
    ("Z",),
)

# The stem. Starts outside the body at the base and tapers to a point short of
# the tip, bowing the same way the body does so it sits along the leaf rather
# than cutting across it. The two edges are offset by ~1.5 units at the base
# and converge on RIB_APEX, which is what makes the taper.
STEM_A = (2.3, 28.6)
STEM_B = (3.4, 29.7)
RIB_APEX = (24.0, 8.0)
LEAF_RIB = (
    ("M", STEM_A),
    ("C", (9.0, 20.0), (16.0, 13.0), RIB_APEX),
    ("C", (17.0, 14.0), (10.0, 21.0), STEM_B),
    ("Z",),
)
GRID = 32

# Tilt, in degrees, counter-clockwise from the drawn position - the tip swings
# LEFT and the stem follows it right. Applied to the control points in Python
# rather than as an SVG `transform`, because a transform would rotate the
# vector artwork and leave Pillow drawing the unrotated outline: the PNG and
# the SVG would quietly disagree. Rotating the definition keeps them one shape.
LEAF_TILT = 10.0


def _rotate(path, degrees, centre):
    """A path tuple rotated about `centre`.

    SVG's y axis points DOWN, so the usual rotation matrix turns clockwise on
    screen. The angle is negated here so a positive LEAF_TILT reads as a
    counter-clockwise, leftward lean the way a person would describe it.
    """
    import math

    theta = math.radians(-degrees)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    cx, cy = centre

    def turn(point):
        dx, dy = point[0] - cx, point[1] - cy
        return (cx + dx * cos_t - dy * sin_t, cy + dx * sin_t + dy * cos_t)

    return tuple((cmd, *[turn(pt) for pt in pts]) for cmd, *pts in path)


def _centre_of(*paths):
    """Bounding-box centre of the flattened paths, so the tilt happens in
    place instead of swinging the mark across its own canvas."""
    pts = [pt for path in paths for pt in _flatten(path)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

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


def _d(path) -> str:
    """A path tuple as an SVG `d` string."""
    parts = []
    for cmd, *pts in path:
        coords = " ".join(f"{x:g},{y:g}" for x, y in pts)
        parts.append(f"{cmd}{coords}" if coords else cmd)
    return " ".join(parts)


def _bezier(p0, p1, p2, p3, steps):
    """Cubic Bezier, sampled. 24 steps is past the point where more changes a
    pixel at 64px, which is the largest size the PNG is ever asked for."""
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append((
            u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
            u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1],
        ))
    return out


def _flatten(path, steps: int = 24) -> list[tuple[float, float]]:
    """A path tuple as a point list, for renderers that cannot draw curves.

    This is what keeps the PNG honest: Pillow has no cubic primitive, so
    without flattening the SAME control points the favicon would have to be a
    second, hand-kept copy of the shape.
    """
    points: list[tuple[float, float]] = []
    cursor = (0.0, 0.0)
    for cmd, *pts in path:
        if cmd == "M":
            cursor = pts[0]
            points.append(cursor)
        elif cmd == "C":
            points.extend(_bezier(cursor, pts[0], pts[1], pts[2], steps))
            cursor = pts[2]
        elif cmd == "L":
            cursor = pts[0]
            points.append(cursor)
    return points


_CENTRE = _centre_of(LEAF_BODY, LEAF_RIB)
LEAF_BODY = _rotate(LEAF_BODY, LEAF_TILT, _CENTRE)
LEAF_RIB = _rotate(LEAF_RIB, LEAF_TILT, _CENTRE)


def _leaf_svg(fill: str, rib: str = None) -> str:
    """Body then stem - the stem is drawn second so it sits on top."""
    return (f'<path d="{_d(LEAF_BODY)}" fill="{fill}"/>'
            f'<path d="{_d(LEAF_RIB)}" fill="{rib or MARK_RIB}"/>')


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

    st.set_page_config(page_icon=...) wants a raster path. The outline is
    flattened from the same control points the SVG uses, so this is the same
    shape at raster resolution rather than a separately maintained one.
    """
    from io import BytesIO

    from PIL import Image, ImageDraw

    scale = size / GRID
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for path, colour in ((LEAF_BODY, MARK_INK), (LEAF_RIB, MARK_RIB)):
        draw.polygon([(x * scale, y * scale) for x, y in _flatten(path)],
                     fill=colour)
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
# The gate's hero lockup: leaf, wordmark and tagline as one supplied artwork,
# drawn twice - once for each ground, not recoloured from one source. The dark
# version is not a tint of the light one: its wordmark is white and its
# tagline a deeper violet, both chosen against the dark page.
# Built by scripts/build_lockup.py - see there for why they are WebP and why
# the backgrounds still have to be keyed out even though each was drawn for
# the ground it sits on.
LOCKUP_PATH = ASSETS / "fintor-lockup.webp"
LOCKUP_DARK_PATH = ASSETS / "fintor-lockup-dark.webp"


def lockup_data_uri(dark: bool = False) -> str:
    """The lockup as a `data:` URI.

    Inlined rather than linked because Streamlit does not serve files out of
    the package by default, and the same media-file pipeline that silently
    dropped the favicon is not worth trusting with the brand on the login
    screen. 28KB of WebP is ~38KB of base64, paid once per render.
    """
    import base64

    path = LOCKUP_DARK_PATH if dark else LOCKUP_PATH
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/webp;base64,{encoded}"


if __name__ == "__main__":
    for name, path in write_assets().items():
        print(f"{name:22s} {path.stat().st_size:>6d} bytes  {path}")
