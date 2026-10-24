"""Combine the silent footage and the narration into one playable file.

    .venv/bin/python scripts/mux_demo.py

Writes build/demo/demo_mux.mp4 - H.264 video and AAC audio in a single
container.

THIS IS AN INTERMEDIATE, NOT THE DELIVERABLE.
---------------------------------------------
It used to write straight to docs/demo.mp4, the path `views/about.py::
recording()` plays and the README links. That was true when this script was
the whole pipeline. It is not any more: the shipped cut comes off the far end
of record_scene -> validate_scene -> narration_build -> mux_narration ->
assemble_final -> remix, and remix.py's output is what gets copied to
docs/demo.mp4.

Left as it was, re-running this script would have replaced a scored, narrated
29 MB file with a half-bitrate mux of the same footage - and `ffmpeg -y` would
not have paused to ask. Recoverable from git, but only if you noticed. So the
default now lands in build/, and writing anywhere outside build/ onto a file
that already exists takes an explicit --force.

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
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "demo"
AUDIO = BUILD / "audio"
RAW = BUILD / "video" / "raw.webm"
TIMINGS = BUILD / "timings.json"
SEGMENTS = BUILD / "segments"
OUT = BUILD / "demo_mux.mp4"

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


def guard_output(out: Path, force: bool) -> None:
    """Refuse to overwrite anything outside build/ that already exists.

    Scoped by location rather than by filename: hardcoding "docs/demo.mp4"
    would guard the one path we happen to have been bitten by and miss the
    next one. Anything under build/demo is scratch and is overwritten without
    comment - that is what the directory is for, and it is gitignored.
    """
    try:
        out.resolve().relative_to(BUILD.resolve())
        return
    except ValueError:
        pass
    if out.exists() and not force:
        raise SystemExit(
            f"refusing to overwrite {out}\n"
            f"  It exists and is outside build/, so it is probably the finished\n"
            f"  cut - this script only produces a rough mux. Write to the default\n"
            f"  ({OUT.relative_to(ROOT)}) instead, or pass --force if you are sure.")


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


def mux_per_beat(args) -> int:
    """Cut at the recorded beat spans, fit each to its narration, concat."""
    spans = json.loads(TIMINGS.read_text(encoding="utf-8"))
    clips = sorted(p for p in AUDIO.iterdir() if p.suffix.lower() in AUDIO_EXTS)
    if len(clips) != len(spans):
        print(f"  {len(spans)} spans but {len(clips)} audio clips - falling back")
        return 1

    vdur = duration(args.video)
    wall = spans[-1]["end"]
    # The whole file is inflated by the same factor; map wall-clock to film time.
    inflate = vdur / wall if wall else 1.0
    print(f"  footage {vdur/60:.2f} min for {wall/60:.2f} min of wall clock "
          f"(x{inflate:.2f} inflation)")

    SEGMENTS.mkdir(parents=True, exist_ok=True)
    for f in SEGMENTS.glob("*.mp4"):
        f.unlink()

    listing, total = [], 0.0
    for i, (sp, clip) in enumerate(zip(spans, clips), 1):
        want = duration(clip)
        src_start, src_end = sp["start"] * inflate, sp["end"] * inflate
        have = max(src_end - src_start, 0.2)
        out = SEGMENTS / f"{i:02d}.mp4"
        run(["ffmpeg", "-y", "-ss", f"{src_start:.3f}", "-t", f"{have:.3f}",
             "-i", str(args.video),
             "-filter:v", f"setpts={want/have:.6f}*PTS", "-an",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-r", "25", str(out)])
        listing.append(out); total += want
        print(f"   {sp['id']:16} film {have:6.1f}s -> narration {want:5.1f}s")

    concat = BUILD / "segments.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in listing), encoding="utf-8")
    silent = BUILD / "fitted.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", str(silent)])

    narration = concat_beats()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(silent), "-i", str(narration),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", "-shortest", str(args.out)])
    report(args.out)
    return 0


def report(out) -> None:
    dur = duration(out)
    st = [s.lower() for s in streams(out)]
    print(f"\nwrote {out}")
    print(f"  {dur/60:.2f} min   {out.stat().st_size/1e6:.1f} MB   streams: {', '.join(st)}")
    if "audio" not in st:
        print("!! NO AUDIO STREAM", file=sys.stderr)
    if not 5*60 <= dur <= 10*60:
        print(f"!! {dur/60:.2f} min is outside the brief's 5-10 minute window")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", type=Path, default=None,
                    help="a single continuous narration file; otherwise per-beat "
                         "clips in build/demo/audio are concatenated")
    ap.add_argument("--video", type=Path, default=RAW)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--force", action="store_true",
                    help="allow --out to overwrite an existing file outside build/")
    args = ap.parse_args()

    # Before any ffmpeg work: a nine-minute encode that ends in a refusal is
    # worse than no refusal at all. Covers mux_per_beat too - both paths write
    # to args.out.
    guard_output(args.out, args.force)

    if not args.video.exists():
        raise SystemExit(f"no footage at {args.video} - run scripts/record_demo.py first")

    narration = args.audio if args.audio else concat_beats()
    if not narration.exists():
        raise SystemExit(f"no narration at {narration}")

    v = duration(args.video)
    a = duration(narration)
    print(f"\nvideo {v/60:.2f} min   audio {a/60:.2f} min   raw drift {v-a:+.1f}s")

    # RE-TIME PER BEAT, NOT UNIFORMLY.
    #
    # Two separate distortions have to be undone. Playwright does not record in
    # real time - it stamps frames at a fixed 25fps regardless of when they were
    # captured, so a page that repaints heavily (Streamlit, on every rerun)
    # yields more frames than wall clock. And a beat can overrun its budget: the
    # fan-out question went 74.5s past on one take.
    #
    # A single scale factor fixes the first and not the second - it would just
    # push everything after the overrun out of step. So the video is cut at the
    # recorded beat boundaries and each segment is fitted to its own narration
    # clip. Sync then holds per beat whatever happened during the take.
    if TIMINGS.exists() and not args.audio:
        return mux_per_beat(args)

    scale = a / v if v > 0 else 1.0
    if abs(scale - 1.0) < 0.02:
        print("  timing already matches; no re-timing applied")
        vfilter = []
    else:
        print(f"  no timings.json - falling back to a single x{1/scale:.3f} re-time")
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
