"""Turn the supplied wordmark PNGs into the two assets the gate ships.

    .venv/bin/python scripts/build_lockup.py

Two sources, one per theme, each drawn for its own ground:

    Fintor_White_Background_Final.png -> fintor-lockup.webp
    Fintor_Dark_Background_Final.png  -> fintor-lockup-dark.webp

An earlier version of this script DERIVED the dark variant from the light one
by recolouring the wordmark, which needed a spatial rule to tell the near-black
text from the leaf (saturation could not: 0.3 against the violet's 0.48; hue
could not either: 240 deg against 257). That guesswork is gone now that both
are drawn. The dark artwork is not a recolour of the light one anyway - its
tagline is a deeper violet, chosen for the dark ground.

What still has to happen to both:

  1. TRIM a 2px border. The dark export has a single stray light column at
     x=0 (162,160,162 against a background of 18,16,20) which would otherwise
     wreck the background estimate and the crop.
  2. ESTIMATE the background as the modal colour rather than reading a corner
     - see above for why a corner is not trustworthy.
  3. CROP to content. Both sources are mostly empty.
  4. KEY the background out on a SOFT ramp, not a hard threshold, so the
     leaf's anti-aliased edge and its fine veins survive instead of getting a
     cut-out halo. Both grounds are keyed: the dark source's background is
     (18,16,20) and the app's is #131217, close but not equal, and an opaque
     rectangle of the wrong black is visible.
  5. WebP. These are inlined as data URIs - Streamlit does not serve files out
     of the package - so size is paid on every render. PNG is ~110KB, WebP 28.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "web_app" / "assets"

SOURCES = (
    ("Fintor_White_Background_Final.png", "fintor-lockup.webp", "fintor-header.png"),
    ("Fintor_Dark_Background_Final.png", "fintor-lockup-dark.webp",
     "fintor-header-dark.png"),
)

# PNG, not WebP, for the header alone. The gate INLINES its lockup as a data
# URI, so format is ours to choose there; the header goes through st.logo(),
# which hands the file to Streamlit's media pipeline - the same pipeline that
# silently resolved the favicon to an empty string once. It rendered a broken
# image for WebP. PNG is bigger and it works.
#
# The header gets the SAME artwork with the tagline erased: at the 34px the
# app header renders, "Finance, made approachable." is an illegible smudge,
# but the leaf and wordmark must still be the ones from the login screen.
# Erasing the band rather than re-composing keeps the leaf and the wordmark in
# their original relative positions - a hand-built lockup would drift from the
# supplied one the moment either is re-exported.
HEADER_W = 420

BORDER_TRIM = 2
ALPHA_LO, ALPHA_HI = 10.0, 46.0     # transparent below, opaque above
CONTENT_MIN_DIST2 = 400
TARGET_W = 620
WEBP_QUALITY = 82


def _background(img: Image.Image) -> tuple[int, int, int]:
    """The modal colour. A corner is not safe - the dark export has a stray
    light column at x=0 that would be read as the background."""
    px = img.load()
    w, h = img.size
    counts = Counter(px[x, y] for y in range(0, h, 3) for x in range(0, w, 3))
    return counts.most_common(1)[0][0]


def _content_box(img: Image.Image, bg, pad: int = 6) -> tuple[int, int, int, int]:
    px = img.load()
    w, h = img.size
    minx, miny, maxx, maxy = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if (r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2 > CONTENT_MIN_DIST2:
                minx, maxx = min(minx, x), max(maxx, x)
                miny, maxy = min(miny, y), max(maxy, y)
    if minx > maxx:
        raise SystemExit("found no content against the estimated background")
    return (max(0, minx - pad), max(0, miny - pad),
            min(w, maxx + pad + 1), min(h, maxy + pad + 1))


def _with_alpha(img: Image.Image, bg) -> Image.Image:
    w, h = img.size
    src, out = img.load(), Image.new("RGBA", img.size)
    dst = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            d = ((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2) ** 0.5
            if d <= ALPHA_LO:
                dst[x, y] = (r, g, b, 0)
            elif d >= ALPHA_HI:
                dst[x, y] = (r, g, b, 255)
            else:
                dst[x, y] = (r, g, b, int(255 * (d - ALPHA_LO) / (ALPHA_HI - ALPHA_LO)))
    return out


def _text_gutter(img: Image.Image) -> int:
    """The x of the empty column between the leaf and the text."""
    w, h = img.size
    px = img.load()
    runs, start = [], None
    for x in range(w):
        empty = not any(px[x, y][3] > 40 for y in range(0, h, 2))
        if empty and start is None:
            start = x
        elif not empty and start is not None:
            runs.append((start, x - 1))
            start = None
    inner = [r for r in runs if 0 < r[0] < w * 0.6]
    if not inner:
        raise SystemExit("no gutter found between the leaf and the text")
    widest = max(inner, key=lambda r: r[1] - r[0])
    return (widest[0] + widest[1]) // 2


def _tagline_band(img: Image.Image, gutter: int) -> tuple[int, int] | None:
    """The rows holding the tagline: the LAST ink band in the text column.

    The text column has two bands - wordmark above, tagline below. Taking the
    last rather than "the second" keeps this working if the wordmark ever
    wraps to two lines.
    """
    w, h = img.size
    px = img.load()
    rows = [any(px[x, y][3] > 40 for x in range(gutter, w, 2)) for y in range(h)]
    bands, start = [], None
    for y, inked in enumerate(rows):
        if inked and start is None:
            start = y
        elif not inked and start is not None:
            bands.append((start, y - 1))
            start = None
    if start is not None:
        bands.append((start, h - 1))
    bands = [b for b in bands if b[1] - b[0] > 4]
    return bands[-1] if len(bands) >= 2 else None


def _without_tagline(img: Image.Image, gutter: int) -> Image.Image:
    """The same artwork with the tagline band cleared, then re-cropped.

    Erased rather than re-composed on purpose: the leaf and the wordmark keep
    the exact positions and proportions the designer gave them. A hand-built
    header lockup would drift from the supplied one the first time either is
    re-exported.
    """
    band = _tagline_band(img, gutter)
    if band is None:
        raise SystemExit("could not find a tagline band to remove")
    out = img.copy()
    px = out.load()
    for y in range(band[0], band[1] + 1):
        for x in range(gutter, out.width):
            px[x, y] = (0, 0, 0, 0)
    return out.crop(out.getbbox())


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for source_name, out_name, header_name in SOURCES:
        source = ROOT / source_name
        if not source.exists():
            raise SystemExit(f"no source image at {source}")

        original = Image.open(source).convert("RGB")
        w, h = original.size
        trimmed = original.crop((BORDER_TRIM, BORDER_TRIM,
                                 w - BORDER_TRIM, h - BORDER_TRIM))
        bg = _background(trimmed)
        cropped = trimmed.crop(_content_box(trimmed, bg))
        keyed = _with_alpha(cropped, bg)
        gutter = _text_gutter(keyed)
        scaled = keyed.resize(
            (TARGET_W, round(keyed.height * TARGET_W / keyed.width)), Image.LANCZOS)

        path = ASSETS / out_name
        scaled.save(path, format="WEBP", quality=WEBP_QUALITY, method=6)
        header = _without_tagline(keyed, gutter)
        header_scaled = header.resize(
            (HEADER_W, round(header.height * HEADER_W / header.width)), Image.LANCZOS)
        header_path = ASSETS / header_name
        header_scaled.save(header_path, format="PNG", optimize=True)

        print(f"  {source_name}")
        print(f"    bg {bg}  {original.size} -> {cropped.size} -> {scaled.size}"
              f"  {path.stat().st_size / 1024:.0f} KB  {out_name}")
        print(f"    header (tagline removed) {header_scaled.size}"
              f"  {header_path.stat().st_size / 1024:.0f} KB  {header_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
