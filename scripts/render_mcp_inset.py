#!/usr/bin/env python3
"""Render the MCP terminal inset from the captured session, and composite it.

    .venv/bin/python scripts/render_mcp_inset.py

Every line it draws comes out of build/demo/mcp_session.json, which is a real
JSON-RPC exchange with `python -m src.mcp_server` (see capture_mcp.py). The
tool names, their one-line descriptions and the numbers in the call result are
the server's own output. Nothing is typed in by hand - if the capture is
missing, this refuses to render rather than inventing a plausible terminal.

The inset covers block 50 (533.54-544.67s), which narrates that the same
analysis functions are reachable over MCP. MCP speaks stdio, so there is no
browser view of it; a terminal is what it actually looks like.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
DEMO = REPO / "build" / "demo"

INSET_W, INSET_H = 1020, 560
BLOCK = 50


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def build_lines(sess: dict) -> list[tuple[str, str]]:
    """(css-class, text) pairs, all drawn from the captured session."""
    lines: list[tuple[str, str]] = [
        ("cmd", "$ python -m src.mcp_server"),
        ("dim", f"  fintor MCP server ready on stdio"),
        ("", ""),
        ("cmd", "> tools/list"),
    ]
    for t in sess["tools"]:
        desc = (t.get("description") or "").strip().splitlines()[0]
        lines.append(("tool", f"  {t['name']:<22}{desc[:44]}"))
    lines += [("", ""), ("cmd", "> tools/call analyze_portfolio")]

    payload = json.loads(sess["call"]["content"][0]["text"])
    for k in ("total_value", "diversification_score", "risk_score", "risk_label"):
        if k in payload:
            lines.append(("val", f"  {k:<24}{payload[k]}"))
    flags = payload.get("concentration_flags") or []
    if flags:
        lines.append(("flag", f"  {flags[0][:58]}"))
    return lines


def page_html(lines: list[tuple[str, str]], duration: float) -> str:
    rows = "".join(
        f'<div class="row {c}" data-i="{i}">{t or "&nbsp;"}</div>'
        for i, (c, t) in enumerate(lines))
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
 *{{margin:0;padding:0;box-sizing:border-box}}
 html,body{{width:{INSET_W}px;height:{INSET_H}px;background:#0b0f14;overflow:hidden}}
 body{{font:15px/1.52 "SF Mono",Menlo,"DejaVu Sans Mono",monospace;color:#cfe3f5;
       padding:0}}
 .bar{{height:34px;background:#151b23;display:flex;align-items:center;
       padding:0 14px;gap:8px;border-bottom:1px solid #222c38}}
 .dot{{width:11px;height:11px;border-radius:50%}}
 .t{{margin-left:10px;font-size:12px;color:#7d8da0;letter-spacing:.04em}}
 .body{{padding:16px 20px}}
 .row{{white-space:pre;opacity:0;transition:opacity .18s linear}}
 .row.on{{opacity:1}}
 .cmd{{color:#8ad0a0}} .dim{{color:#6b7c8f}} .tool{{color:#cfe3f5}}
 .val{{color:#e4c98a}} .flag{{color:#e59aa0}}
</style></head><body>
 <div class="bar"><span class="dot" style="background:#ff5f57"></span>
  <span class="dot" style="background:#febc2e"></span>
  <span class="dot" style="background:#28c840"></span>
  <span class="t">fintor — MCP over stdio</span></div>
 <div class="body">{rows}</div>
<script>
 const rows=[...document.querySelectorAll('.row')];
 const DUR={duration};
 window.__start=()=>{{
   const t0=performance.now();
   const step=(DUR*0.74)/rows.length;
   const tick=()=>{{
     const t=(performance.now()-t0)/1000;
     rows.forEach((r,i)=>{{ if(t>=i*step) r.classList.add('on'); }});
     requestAnimationFrame(tick);
   }};
   tick();
 }};
</script></body></html>"""


def main() -> int:
    sess_path = DEMO / "mcp_session.json"
    if not sess_path.exists():
        raise SystemExit("no mcp_session.json - run scripts/capture_mcp.py first")
    sess = json.loads(sess_path.read_text())
    if not sess.get("tools"):
        raise SystemExit("captured session has no tools - refusing to render")

    man = json.loads((DEMO / "narration_manifest.json").read_text())
    b = next(x for x in man["blocks"] if x["block"] == BLOCK)
    duration = b["duration"]

    lines = build_lines(sess)
    html = DEMO / "mcp_inset.html"
    html.write_text(page_html(lines, duration), encoding="utf-8")

    raw_dir = DEMO / "raw_mcp"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for stale in raw_dir.glob("*.webm"):
        stale.unlink()

    from playwright.sync_api import sync_playwright
    from scripts.record_demo import launch_browser
    from scripts.record_scene import CLAPPER_JS, DROP_CLAPPER_JS, Clock, postprocess

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        ctx = browser.new_context(viewport={"width": INSET_W, "height": INSET_H},
                                  record_video_dir=str(raw_dir),
                                  record_video_size={"width": INSET_W,
                                                     "height": INSET_H},
                                  device_scale_factor=1)
        page = ctx.new_page()
        page.goto(html.resolve().as_uri(), wait_until="networkidle")
        page.evaluate(CLAPPER_JS)
        page.wait_for_timeout(1800)
        page.evaluate(DROP_CLAPPER_JS)
        clock = Clock()
        page.evaluate("window.__start()")
        clock.until(duration)
        page.wait_for_timeout(200)
        video = page.video
        ctx.close()
        browser.close()
        raw = Path(video.path())

    inset = DEMO / "mcp_inset.mp4"
    postprocess(raw, inset, duration)
    print(f"inset {duration:.2f}s with {len(lines)} real lines -> {inset}")

    # Composite onto the narrated s9/s10 segment.
    base = DEMO / "scenes" / "s9_s10_narrated.mp4"
    out = DEMO / "scenes" / "s9_s10_narrated_mcp.mp4"
    start = b["speech_in"] - 434.85          # s9_s10 begins at 434.85s
    end = start + duration
    x, y = (1600 - INSET_W) // 2, (900 - INSET_H) // 2 + 20
    subprocess.run([
        ffmpeg(), "-y", "-i", str(base), "-i", str(inset),
        "-filter_complex",
        # setpts is load bearing. overlay pulls from the second input starting
        # at OUTPUT time 0, so without shifting the inset's timestamps it had
        # already run out by t=98s and the filter composited its held final
        # frame - which, after the fade-out, is black. Measured: the overlaid
        # region peaked at pixel value 23, i.e. the terminal text was simply
        # not there. eof_action=pass then lets the base video continue once
        # the inset ends.
        f"[1:v]format=yuv420p,fade=t=in:st=0:d=0.4,"
        f"fade=t=out:st={duration-0.5:.2f}:d=0.5,"
        f"setpts=PTS+{start:.3f}/TB[ins];"
        f"[0:v][ins]overlay=x={x}:y={y}:eof_action=pass:"
        f"enable='between(t,{start:.2f},{end:.2f})'[v]",
        "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", str(out)],
        check=True, capture_output=True)
    print(f"composited {start:.2f}-{end:.2f}s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
