"""Combine the silent footage and the narration into one submittable file.

    .venv/bin/python scripts/mux_demo.py

Writes docs/demo.mp4 - H.264 video and AAC audio in a single container, which is
what `views/about.py::recording()` looks for and what a grader can open anywhere.

SWAPPING IN A HUMAN NARRATION
-----------------------------
This step is deliberately separate from recording so the voice can be replaced
without re-filming. Either:

    * drop per-beat files into build/demo/audio as NN-<id>.m4a (or .aiff/.wav)
      and they are concatenated in filename order, or
    * pass a single continuous take:
        python scripts/mux_demo.py --audio path/to/narration.m4a

The footage is untouched either way.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "demo"
AUDIO = BUILD / "audio"
RAW = BUILD / "video" / "raw.webm"
OUT = ROOT / "docs" / "demo.mp4"

AUDIO_EXTS = (".aiff", ".m4a", ".wav", ".mp3")


def ffmpeg_exe() -> str:
    """The ffmpeg to use.

    Prefers the static build that ships with imageio-ffmpeg, because this
    machine is macOS 12 and `brew install ffmpeg` wants to build Python from
    source to get there. The PyPI binary has libx264 and aac, which is all this
    needs, and it arrives through a package index rather than a download.
    """
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        if not found:
            raise SystemExit(
                "no ffmpeg: pip install imageio-ffmpeg (or brew install ffmpeg)")
        return found


FFMPEG = ffmpeg_exe()


def run(cmd: list[str]) -> None:
    cmd = [FFMPEG if c == "ffmpeg" else c for c in cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(" ".join(cmd[:6]), "...", file=sys.stderr)
        print(proc.stderr[-1500:], file=sys.stderr)
        raise SystemExit(f"ffmpeg failed ({proc.returncode})")


def duration(path: Path) -> float:
    """Seconds, parsed from ffmpeg's own banner.

    imageio-ffmpeg ships ffmpeg but not ffprobe, so the duration comes from
    `ffmpeg -i`, which prints it to stderr and exits non-zero because no output
    was requested. That is expected, not an error.
    """
    out = subprocess.run([FFMPEG, "-i", str(path)],
                         capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out)
    if not m:
        raise SystemExit(f"could not read a duration from {path}")
    h, mn, sec = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(sec)


def streams(path: Path) -> list[str]:
    out = subprocess.run([FFMPEG, "-i", str(path)],
                         capture_output=True, text=True).stderr
    return re.findall(r"Stream #\d+:\d+.*?: (\w+):", out)


def concat_beats() -> Path:
    clips = sorted(p for p in AUDIO.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    if not clips:
        raise SystemExit(f"no audio clips in {AUDIO}")
    print(f"concatenating {len(clips)} clips:")
    for c in clips:
        print(f"  {c.name}")
    listing = BUILD / "concat.txt"
    # Paths are quoted for the concat demuxer; ' inside a filename would break it,
    # but these are generated names so the risk is nil and the failure is loud.
    listing.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    joined = BUILD / "narration.m4a"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c:a", "aac", "-b:a", "192k", str(joined)])
    return joined


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", type=Path, default=None,
                    help="a single continuous narration file; otherwise per-beat "
                         "clips in build/demo/audio are concatenated")
    ap.add_argument("--video", type=Path, default=RAW)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    if not args.video.exists():
        raise SystemExit(f"no footage at {args.video} - run scripts/record_demo.py first")

    narration = args.audio if args.audio else concat_beats()
    if not narration.exists():
        raise SystemExit(f"no narration at {narration}")

    v = duration(args.video)
    a = duration(narration)
    print(f"\nvideo {v/60:.2f} min   audio {a/60:.2f} min   raw drift {v-a:+.1f}s")

    # RE-TIME THE VIDEO TO THE NARRATION.
    #
    # Playwright does not record in real time. It stamps captured frames at a
    # fixed 25fps regardless of when they were captured, so a page that
    # repaints heavily - which Streamlit does on every rerun - produces more
    # frames than wall-clock and the file plays back long. Measured on the
    # first take: 24,862 frames for about nine minutes of real interaction,
    # which is 16.6 minutes of playback.
    #
    # Scaling presentation timestamps fixes it and, usefully, pins sync: the
    # video is made exactly as long as the audio, so the two cannot drift no
    # matter how uneven the capture was.
    scale = a / v if v > 0 else 1.0
    if abs(scale - 1.0) < 0.02:
        print("  timing already matches; no re-timing applied")
        vfilter = []
    else:
        pct = (1 / scale) if scale < 1 else scale
        print(f"  re-timing video x{1/scale:.3f} ({'speeding up' if scale < 1 else 'slowing'}"
              f" by {abs(1-1/scale)*100:.0f}%) so it matches the narration exactly")
        vfilter = ["-filter:v", f"setpts={scale}*PTS"]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # yuv420p because without it QuickTime and some browsers refuse to play.
    # -shortest so a trailing silence does not pad the end.
    run([
        "ffmpeg", "-y",
        "-i", str(args.video),
        "-i", str(narration),
        *vfilter,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
        "-r", "25",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",
        str(args.out),
    ])

    size_mb = args.out.stat().st_size / 1e6
    dur = duration(args.out)
    has_audio = [s.lower() for s in streams(args.out)]
    print(f"\nwrote {args.out}")
    print(f"  {dur/60:.2f} min   {size_mb:.1f} MB   streams: {', '.join(has_audio)}")
    if "audio" not in has_audio:
        print("!! NO AUDIO STREAM - the silent-file failure mode", file=sys.stderr)
        return 1
    if not 5 * 60 <= dur <= 10 * 60:
        print(f"!! {dur/60:.2f} min is outside the brief's 5-10 minute window")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
