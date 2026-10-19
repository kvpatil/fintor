"""Turn the supplied wordmark PNG into the two assets the gate ships.

    .venv/bin/python scripts/build_lockup.py "Fintor Purple Leaf Wordmark.png"

The source is a 2172x724 RGB export with the lockup floating in a sea of
near-white and NO alpha channel. Dropped into the app as-is it would paint a
white rectangle over the dark theme, and its near-black wordmark would be
invisible there anyway. Four things have to happen, and they are here rather
than done once by hand so a re-export can be processed the same way:

  1. CROP to the content. The source is 60% empty.
  2. KEY OUT the background. Not a hard threshold - a soft ramp on distance
     from the background colour, so the leaf's anti-aliased edge and its fine
     veins survive instead of getting a cut-out halo.
  3. RECOLOUR the wordmark for dark mode. Only the wordmark: the leaf and the
     tagline are violet and already hold contrast on both grounds.
  4. WebP, not PNG. These are inlined as data URIs because Streamlit does not
     serve local files by default, and 110KB of PNG becomes 151KB of base64
     on every rerun. WebP is 29KB.

HOW THE WORDMARK IS FOUND, since two obvious rules both fail. Saturation does
not separate it - measured, the wordmark sits at 0.3 and the violet at 0.48,
and a 0.22 cut caught only 1658 of ~26000 pixels. Hue does not either: 240 deg
against the leaf's 257. Brightness alone would work on the text but bleaches
the leaf's own dark veins, which are 8.2% of it. What IS unambiguous is a 65px
column of empty space between the leaf and the text, so the split is spatial
and the brightness test only applies to the right of it.
"""

from __future__ import annotations

import colorsys
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "web_app" / "assets"

BG = (253, 253, 254)
ALPHA_LO, ALPHA_HI = 10.0, 46.0     # transparent below, opaque above
DARK_INK = (231, 230, 235)          # --fin-ink in dark mode
DARK_VALUE_MAX = 0.50
TARGET_W = 620
WEBP_QUALITY = 82


def _content_box(img: Image.Image, pad: int = 6) -> tuple[int, int, int, int]:
    px = img.load()
    w, h = img.size
    minx, miny, maxx, maxy = w, h, 0, 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if (r - BG[0]) ** 2 + (g - BG[1]) ** 2 + (b - BG[2]) ** 2 > 300:
                minx, maxx = min(minx, x), max(maxx, x)
                miny, maxy = min(miny, y), max(maxy, y)
    return (max(0, minx - pad), max(0, miny - pad),
            min(w, maxx + pad + 1), min(h, maxy + pad + 1))


def _with_alpha(img: Image.Image) -> Image.Image:
    w, h = img.size
    src, out = img.load(), Image.new("RGBA", img.size)
    dst = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            d = ((r - BG[0]) ** 2 + (g - BG[1]) ** 2 + (b - BG[2]) ** 2) ** 0.5
            if d <= ALPHA_LO:
                dst[x, y] = (r, g, b, 0)
            elif d >= ALPHA_HI:
                dst[x, y] = (r, g, b, 255)
            else:
                dst[x, y] = (r, g, b, int(255 * (d - ALPHA_LO) / (ALPHA_HI - ALPHA_LO)))
    return out


def _text_gutter(img: Image.Image) -> int:
    """The x of the empty column between the leaf and the wordmark."""
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
        raise SystemExit("no gutter found between the leaf and the wordmark")
    widest = max(inner, key=lambda r: r[1] - r[0])
    return (widest[0] + widest[1]) // 2


def _darkened(img: Image.Image, gutter: int) -> Image.Image:
    w, h = img.size
    src, out = img.load(), Image.new("RGBA", img.size)
    dst = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = src[x, y]
            if a == 0:
                dst[x, y] = (0, 0, 0, 0)
                continue
            _h, _s, value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if x > gutter and value < DARK_VALUE_MAX:
                dst[x, y] = (*DARK_INK, a)
            else:
                dst[x, y] = (r, g, b, a)
    return out


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Fintor Purple Leaf Wordmark.png"
    if not source.exists():
        raise SystemExit(f"no source image at {source}")

    original = Image.open(source).convert("RGB")
    cropped = original.crop(_content_box(original))
    keyed = _with_alpha(cropped)
    gutter = _text_gutter(keyed)
    print(f"  {original.size} -> cropped {cropped.size}, gutter at x={gutter}")

    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, image in (("fintor-lockup.webp", keyed),
                        ("fintor-lockup-dark.webp", _darkened(keyed, gutter))):
        scaled = image.resize(
            (TARGET_W, round(image.height * TARGET_W / image.width)), Image.LANCZOS)
        path = ASSETS / name
        scaled.save(path, format="WEBP", quality=WEBP_QUALITY, method=6)
        print(f"  {name:26} {scaled.size}  {path.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
