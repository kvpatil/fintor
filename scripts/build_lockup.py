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
    ("Fintor_White_Background_Final.png", "fintor-lockup.webp"),
    ("Fintor_Dark_Background_Final.png", "fintor-lockup-dark.webp"),
)

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


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for source_name, out_name in SOURCES:
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
        scaled = keyed.resize(
            (TARGET_W, round(keyed.height * TARGET_W / keyed.width)), Image.LANCZOS)

        path = ASSETS / out_name
        scaled.save(path, format="WEBP", quality=WEBP_QUALITY, method=6)
        print(f"  {source_name}")
        print(f"    bg {bg}  {original.size} -> {cropped.size} -> {scaled.size}"
              f"  {path.stat().st_size / 1024:.0f} KB  {out_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
