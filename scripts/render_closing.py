#!/usr/bin/env python3
"""Render the closing card: logo reveal, then the tagline typed in sync.

    .venv/bin/python scripts/render_closing.py

Block 52 is "Fintor, finance, made approachable." - 2.40s of speech. The word
offsets come from the same per-word timing file the storyboard uses, so the
reveal and the typing are driven by when the words are actually said:

    Fintor        556.10s   logo + wordmark reveal
    Finance       556.62s   typing starts
    approachable  557.54s   typing must finish around here
    (audio ends)  558.50s
    (card holds)  561.90s   so the tagline settles instead of cutting

Drawn in the browser rather than with an image library: the wordmark is the
app's own `fintor-header-dark.png` and the type is the app's own font stack,
so the card cannot drift from the product's identity. Recorded through the
same clapper-and-wall-clock path as the scenes, so its timing is measured the
same way.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

DEMO = REPO / "build" / "demo"
HOLD_AFTER_AUDIO = 3.40
TAGLINE = "Finance, made approachable."
VIEWPORT = {"width": 1600, "height": 900}
FPS = 25


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def page_html(logo_uri: str, reveal: float, type_start: float,
              type_end: float) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:100%; height:100%; background:#0d0a14; overflow:hidden; }}
  body {{ display:flex; align-items:center; justify-content:center;
          font-family:"Source Serif 4","Iowan Old Style",Georgia,serif; }}
  /* position+z-index is load bearing: .glow is position:fixed, so it paints
     in the positioned layer, ABOVE a plain <img>. The tagline survived only
     because .tag happens to be position:relative; the wordmark did not and
     rendered behind the gradient. */
  .wrap {{ text-align:center; position:relative; z-index:1; }}
  /* A slow radial bloom behind the mark - the only motion besides the type,
     so the eye lands on the wordmark and then on the line being written. */
  .glow {{ position:fixed; inset:0; background:
      radial-gradient(ellipse 55% 45% at 50% 46%, #3a1f6b 0%, #170f28 45%, #0d0a14 75%);
      opacity:0; transition:opacity 1.6s ease-out; }}
  .glow.on {{ opacity:1; }}
  img {{ width:520px; height:auto; display:block; margin:0 auto 34px;
         opacity:0; transform:translateY(16px) scale(.965);
         transition:opacity .85s cubic-bezier(.2,.7,.3,1),
                    transform .85s cubic-bezier(.2,.7,.3,1); }}
  img.on {{ opacity:1; transform:none; }}
  .tag {{ position:relative; font-size:40px; letter-spacing:.012em;
          color:#d9cdf2; min-height:56px; }}
  .caret {{ display:inline-block; width:2px; height:38px; margin-left:3px;
            background:#9b7ddb; vertical-align:-5px; opacity:0; }}
  .caret.on {{ opacity:1; animation:blink 1s steps(1,end) infinite; }}
  .caret.off {{ opacity:0; animation:none; }}
  @keyframes blink {{ 50% {{ opacity:0; }} }}
</style></head><body>
  <div class="glow" id="glow"></div>
  <div class="wrap">
    <img id="logo" src="{logo_uri}" alt="Fintor">
    <div class="tag"><span id="tag"></span><span class="caret" id="caret"></span></div>
  </div>
<script>
  const TEXT = {json.dumps(TAGLINE)};
  const REVEAL = {reveal}, T0 = {type_start}, T1 = {type_end};
  window.__start = () => {{
    const t0 = performance.now();
    const logo = document.getElementById('logo');
    const glow = document.getElementById('glow');
    const tag  = document.getElementById('tag');
    const caret= document.getElementById('caret');
    const tick = () => {{
      const t = (performance.now() - t0) / 1000;
      if (t >= REVEAL) {{ logo.classList.add('on'); glow.classList.add('on'); }}
      if (t >= T0) {{
        caret.classList.add('on');
        const p = Math.min(1, (t - T0) / (T1 - T0));
        tag.textContent = TEXT.slice(0, Math.round(p * TEXT.length));
        if (p >= 1) {{ caret.classList.remove('on'); caret.classList.add('off'); }}
      }}
      requestAnimationFrame(tick);
    }};
    tick();
  }};
</script></body></html>"""


def main() -> int:
    man = json.loads((DEMO / "narration_manifest.json").read_text())
    words = json.loads((DEMO / "word_timings.json").read_text())
    b52 = next(b for b in man["blocks"] if b["block"] == 52)
    w = {x["w"].lower().strip(".,"): x["s"] for x in words["52"]}

    reveal = w.get("fintor", 0.0)
    type_start = w.get("finance", 0.52)
    type_end = w.get("approachable", 1.44) + 0.55   # land just past the word
    duration = b52["duration"] + HOLD_AFTER_AUDIO

    logo = REPO / "src" / "web_app" / "assets" / "fintor-header-dark.png"
    uri = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode()

    html = DEMO / "closing.html"
    html.write_text(page_html(uri, reveal, type_start, type_end), encoding="utf-8")

    raw_dir = DEMO / "raw_closing"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for stale in raw_dir.glob("*.webm"):
        stale.unlink()

    from playwright.sync_api import sync_playwright
    from scripts.record_demo import launch_browser
    from scripts.record_scene import CLAPPER_JS, DROP_CLAPPER_JS, Clock, postprocess

    print(f"closing card: reveal@{reveal:.2f}s  type {type_start:.2f}->"
          f"{type_end:.2f}s  duration {duration:.2f}s")

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        ctx = browser.new_context(viewport=VIEWPORT, record_video_dir=str(raw_dir),
                                  record_video_size=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()
        page.goto(html.as_uri(), wait_until="networkidle")
        page.evaluate(CLAPPER_JS)
        page.wait_for_timeout(2000)
        page.evaluate(DROP_CLAPPER_JS)
        clock = Clock()
        page.evaluate("window.__start()")
        clock.until(duration)
        page.wait_for_timeout(200)
        video = page.video
        ctx.close()
        browser.close()
        raw = Path(video.path())

    out = DEMO / "scenes" / "s11_closing.mp4"
    info = postprocess(raw, out, duration)
    print(f"  clapper at {info['clapper_end']:.3f}s -> {out} ({duration:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
