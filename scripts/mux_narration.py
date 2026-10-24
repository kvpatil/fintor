#!/usr/bin/env python3
"""Lay the narration clips onto a silent baseline video at their exact offsets.

    .venv/bin/python scripts/mux_narration.py build/demo/scenes/s1_s2.mp4 --from 0

Each clip is delayed to its `speech_in` from the narration manifest and the set
is mixed into one track. Nothing is stretched, pitched or re-timed - the clips
play at the speed they were generated at, which is the whole point: the video
was driven to match the speech, not the other way round.

Music is deliberately NOT mixed here. Narration and score stay separate tracks
until the final pass so either can be re-cut without re-rendering the other.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "build" / "demo"


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--from", dest="start", type=float, default=0.0,
                    help="scene-time of the video's first frame")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    video = Path(args.video)
    out = Path(args.out) if args.out else video.with_name(video.stem + "_narrated.mp4")
    man = json.loads((DEMO / "narration_manifest.json").read_text())

    # imageio-ffmpeg ships ffmpeg but no ffprobe, so the duration is read from
    # ffmpeg's own stderr banner rather than assuming a probe binary exists.
    import re
    ff = ffmpeg()
    err = subprocess.run([ff, "-i", str(video)], capture_output=True,
                         text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    if not m:
        raise SystemExit(f"could not read duration of {video}")
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])

    window = (args.start, args.start + dur)
    used = [b for b in man["blocks"]
            if b["speech_in"] < window[1] and b["speech_out"] > window[0]]
    if not used:
        raise SystemExit(f"no narration blocks inside {window}")

    cmd = [ff, "-y", "-i", str(video)]
    for b in used:
        cmd += ["-i", b["clip"]]
    legs = []
    for i, b in enumerate(used, start=1):
        delay = int(round((b["speech_in"] - args.start) * 1000))
        legs.append(f"[{i}:a]adelay={delay}|{delay},aformat="
                    f"sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(1, len(used) + 1))
    legs.append(f"{mix}amix=inputs={len(used)}:normalize=0:dropout_transition=0,"
                f"atrim=0:{dur:.3f},asetpts=N/SR/TB[out]")
    cmd += ["-filter_complex", ";".join(legs),
            "-map", "0:v", "-map", "[out]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)

    print(f"{len(used)} narration blocks (b{used[0]['block']}-b{used[-1]['block']}) "
          f"over {dur:.2f}s -> {out}")
    for b in used:
        print(f"  b{b['block']:02d} at {b['speech_in'] - args.start:7.2f}s "
              f"({b['duration']:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
