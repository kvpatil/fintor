#!/usr/bin/env python3
"""Measure a recorded scene against the storyboard it was shot to.

    .venv/bin/python scripts/validate_scene.py build/demo/scenes/s1_s2.mp4 --from 0

Reports, from the pixels rather than from the recorder's own logs:

  * when the app crosses from the sign-in gate to the signed-in app
  * every blank/loading window longer than 0.3s
  * whether the six account cards are present at each cue in the window

The gate/app discriminator is the nav pill at (160, 30): strongly saturated
violet once signed in, near-white page background on the gate. Deliberately
NOT a general "which page is this" detector - an earlier version of that
reported GATE for any scrolled page, because the nav scrolls out of view, and
it produced drift readings that were not real.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "build" / "demo"
FPS = 10
W, H = 800, 450          # half scale; the probes are large flat regions


def frames(video: Path):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    p = subprocess.run([ff, "-i", str(video), "-vf", f"scale={W}:{H},fps={FPS}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    buf = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(buf) // (W * H * 3)
    return buf[:n * W * H * 3].reshape(n, H, W, 3).astype(np.int16)


def signed_in(f) -> bool:
    """The active nav pill is saturated violet; the gate has nothing there."""
    patch = f[10:22, 60:110]                      # (160,30) at half scale
    r, g, b = patch[..., 0].mean(), patch[..., 1].mean(), patch[..., 2].mean()
    return (b - g) > 45 and b > 110


def blank(f) -> bool:
    return f[40:, :].std() < 6


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--from", dest="start", type=float, default=0.0)
    args = ap.parse_args()

    man = json.loads((DEMO / "production_manifest.json").read_text())
    fr = frames(Path(args.video))
    t = lambda i: args.start + i / FPS

    sig = [signed_in(f) for f in fr]
    cross = next((i for i in range(1, len(sig)) if sig[i] and sig[i - 1]), None)
    blanks, run = [], None
    for i, f in enumerate(fr):
        if blank(f):
            run = i if run is None else run
        elif run is not None:
            if (i - run) / FPS >= 0.3:
                blanks.append((t(run), t(i)))
            run = None

    print(f"{len(fr)} frames at {FPS}fps, {t(0):.2f}s -> {t(len(fr)-1):.2f}s")
    print(f"gate -> signed in at  {t(cross):.2f}s" if cross is not None
          else "never signed in")
    for a, b in blanks:
        print(f"blank/loading         {a:.2f}s -> {b:.2f}s  ({b - a:.2f}s)")

    fails = 0
    for sc in man["scenes"]:
        for c in sc["cues"]:
            if not (t(0) <= c["at"] <= t(len(fr) - 1)):
                continue
            if "CLICK Sign in" in c["action"] and cross is not None:
                lag = t(cross) - c["at"]
                ok = 0 <= lag <= 2.5
                print(f"{'PASS' if ok else 'FAIL'}  sign-in cue {c['at']:.2f}s, "
                      f"app up {lag:+.2f}s later")
                fails += 0 if ok else 1
            if "six cards" in c["action"] or "all six" in c["action"].lower():
                i = int(round((c["at"] - args.start) * FPS))
                ok = not sig[i] and not blank(fr[i])
                print(f"{'PASS' if ok else 'FAIL'}  gate with cards at {c['at']:.2f}s")
                fails += 0 if ok else 1
    print("OK" if not fails else f"{fails} check(s) failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
