#!/usr/bin/env python3
"""Measure the finished video against the timeline it was built from.

    .venv/bin/python scripts/qa_report.py build/demo/fintor_final.mp4

Everything here is read back out of the RENDERED file - not from the
recorder's logs, which is the distinction that matters. The recorder can
report a cue fired on time and still produce a frame showing the wrong thing;
that is precisely how the original video came to sign in fifty-three seconds
before the narration said so.

Checks:
  duration        against the narration timeline plus the closing hold
  narration       speech energy present across every one of the 52 blocks
  sign-in         the gate -> signed-in crossing against the spoken cue
  blanks          loading windows longer than 0.3s
  loudness        integrated LUFS / true peak of the final mix
  closing card    the card is actually on screen at the end
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "build" / "demo"
FPS = 5
W, H = 640, 360
CLOSING_HOLD = 3.40


def ff() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration(p: Path) -> float:
    err = subprocess.run([ff(), "-i", str(p)], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def video_frames(p: Path):
    r = subprocess.run([ff(), "-i", str(p), "-vf", f"scale={W}:{H},fps={FPS}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    n = len(buf) // (W * H * 3)
    return buf[:n * W * H * 3].reshape(n, H, W, 3).astype(np.int16)


def audio_envelope(p: Path, sr: int = 8000):
    r = subprocess.run([ff(), "-i", str(p), "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    win = sr // 20                                     # 50ms
    n = len(a) // win
    return np.sqrt((a[:n * win].reshape(n, win) ** 2).mean(axis=1)), 20.0


def loudness(p: Path) -> dict:
    r = subprocess.run([ff(), "-i", str(p), "-af",
                        "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", r.stderr, re.S)
    return json.loads(m.group(0)) if m else {}


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else DEMO / "fintor_final.mp4")
    man = json.loads((DEMO / "narration_manifest.json").read_text())
    prod = json.loads((DEMO / "production_manifest.json").read_text())
    blocks = man["blocks"]
    expected = man["total_seconds"] + CLOSING_HOLD

    rows, fails = [], 0

    def check(name: str, ok: bool, detail: str) -> None:
        nonlocal fails
        rows.append((("PASS" if ok else "FAIL"), name, detail))
        if not ok:
            fails += 1

    dur = probe_duration(target)
    check("duration", abs(dur - expected) <= 1.0,
          f"{dur:.2f}s against {expected:.2f}s expected "
          f"({dur - expected:+.2f}s)")

    env, eps = audio_envelope(target)
    quiet = []
    for b in blocks:
        i0, i1 = int(b["speech_in"] * eps), int(b["speech_out"] * eps)
        seg = env[i0:i1]
        if seg.size == 0 or seg.mean() < 0.004:
            quiet.append(b["block"])
    check("narration coverage", not quiet,
          f"all {len(blocks)} blocks carry speech" if not quiet
          else f"silent blocks: {quiet}")

    fr = video_frames(target)
    t = lambda i: i / FPS

    def signed_in(f) -> bool:
        patch = f[8:17, 48:88]
        return (patch[..., 2].mean() - patch[..., 1].mean()) > 45 and \
               patch[..., 2].mean() > 110

    sig = [signed_in(f) for f in fr]
    cross = next((i for i in range(1, len(sig)) if sig[i] and sig[i - 1]), None)
    cue = next(c["at"] for s in prod["scenes"] if s["id"] == "s2"
               for c in s["cues"] if "CLICK Sign in" in c["action"])
    if cross is None:
        check("sign-in sync", False, "never crossed to the signed-in app")
    else:
        lag = t(cross) - cue
        check("sign-in sync", 0 <= lag <= 2.5,
              f"spoken cue {cue:.2f}s, app up at {t(cross):.2f}s ({lag:+.2f}s)")

    blanks, run_start = [], None
    for i, f in enumerate(fr):
        isblank = f[40:, :].std() < 6
        if isblank and run_start is None:
            run_start = i
        elif not isblank and run_start is not None:
            if (i - run_start) / FPS >= 0.3:
                blanks.append((t(run_start), t(i)))
            run_start = None
    # the closing card is a dark, near-uniform frame by design
    blanks = [(a, b) for a, b in blanks if b < blocks[-1]["speech_in"] - 1]
    # Every blank here is a real Streamlit page load - picking an account and
    # signing out are full navigations, because the account cards are plain
    # links. They are reported in full rather than filtered out; the check is
    # whether any single one is long enough to read as a stall (>2s), not
    # whether the app navigates at all.
    worst = max((b - a for a, b in blanks), default=0.0)
    check("loading blanks", worst <= 2.0,
          (f"{len(blanks)} app navigation(s), worst {worst:.2f}s: "
           + "; ".join(f"{a:.2f}-{b:.2f}s" for a, b in blanks))
          if blanks else "none")

    last = fr[-6]
    check("closing card", last.mean() < 70 and last[:, :, 2].mean() >
          last[:, :, 1].mean(),
          f"final frame mean={last.mean():.1f}, blue-dominant "
          f"(b-g={last[:,:,2].mean()-last[:,:,1].mean():+.1f})")

    ln = loudness(target)
    if ln:
        i_lufs, tp = float(ln.get("input_i", 0)), float(ln.get("input_tp", 0))
        check("loudness", -20 <= i_lufs <= -13 and tp <= -1.0,
              f"{i_lufs:.1f} LUFS integrated, true peak {tp:.1f} dBTP")

    width = max(len(r[1]) for r in rows)
    print(f"\nQA — {target.name}\n" + "=" * (width + 58))
    for status, name, detail in rows:
        print(f"  {status}  {name:<{width}}  {detail}")
    print("=" * (width + 58))
    print(f"  {len(rows) - fails}/{len(rows)} checks passed\n")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
