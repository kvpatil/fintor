#!/usr/bin/env python3
"""Assemble the segments into the review cut and then the final mix.

    .venv/bin/python scripts/assemble_final.py

Three stages, deliberately separate so a bad mix never costs a re-record and
the narration can be re-laid without touching the music:

  1. narration onto the closing card, which is rendered silent
  2. pad + concat every segment -> fintor_review.mp4   (narration only)
  3. score under the narration    -> fintor_final.mp4   (final mix)

PADDING. Each segment was recorded to its own span, and consecutive spans are
separated by the 0.45s inter-block pause that the narration timeline builds in
(67.82 -> 68.27, and so on). A straight concat would swallow those four pauses
and every absolute timestamp after the first segment would drift early. So the
last frame of each segment is held for exactly the gap that follows it.

MIXING. The score is ducked under the voice by a real sidechain compressor
keyed on the narration, not by a fixed background level: a static -14dB bed
either fights the voice in the quiet blocks or disappears in the loud ones.
On top of that an envelope lets the music come up in the open and over the
closing card, where there is no narration to protect.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
DEMO = REPO / "build" / "demo"
SCENES = DEMO / "scenes"
SCORE = Path.home() / "Documents/IK-FDE/elevenlabs/fintor_cinematic_score.mp3"

# (file, timeline start) in order. The gap to the next segment is computed.
SEGMENTS = [
    ("s1_s2_narrated.mp4", 0.00),
    ("s3_s4_s5_narrated.mp4", 68.27),
    ("s6_s7_s8_narrated.mp4", 228.02),
    ("s9_s10_narrated_mcp.mp4", 434.85),
    ("s11_closing_narrated.mp4", 556.10),
]

MUSIC_GAIN = 0.30        # pre-duck level
DUCK_THRESHOLD = 0.02
DUCK_RATIO = 9


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    err = subprocess.run([ffmpeg(), "-i", str(path)],
                         capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    if not m:
        raise SystemExit(f"no duration for {path}")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2500:])
        raise SystemExit(f"ffmpeg failed: {' '.join(cmd[:6])} ...")


def main() -> int:
    ff = ffmpeg()
    man = json.loads((DEMO / "narration_manifest.json").read_text())
    total = man["total_seconds"]

    # -- 1. narration onto the closing card ------------------------------
    closing = SCENES / "s11_closing.mp4"
    closing_nar = SCENES / "s11_closing_narrated.mp4"
    b52 = next(b for b in man["blocks"] if b["block"] == 52)
    run([ff, "-y", "-i", str(closing), "-i", b52["clip"],
         "-filter_complex",
         "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
         f"apad=whole_dur={duration(closing):.3f}[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", str(closing_nar)])
    print(f"1. closing card narrated -> {closing_nar.name}")

    # -- 2. pad each segment by the gap that follows it, then concat -----
    padded, cursor = [], 0.0
    for i, (name, start) in enumerate(SEGMENTS):
        src = SCENES / name
        if not src.exists():
            raise SystemExit(f"missing segment: {src}")
        d = duration(src)
        nxt = SEGMENTS[i + 1][1] if i + 1 < len(SEGMENTS) else None
        gap = max(0.0, round(nxt - (start + d), 3)) if nxt is not None else 0.0
        out = DEMO / f"_pad{i}.mp4"
        if gap > 0.001:
            run([ff, "-y", "-i", str(src), "-vf",
                 f"tpad=stop_mode=clone:stop_duration={gap:.3f}",
                 "-af", f"apad=pad_dur={gap:.3f}",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                 "-fflags", "+genpts", str(out)])
        else:
            run([ff, "-y", "-i", str(src), "-c", "copy", str(out)])
        print(f"   {name}: {d:.2f}s + {gap:.2f}s gap")
        padded.append(out)
        cursor = start + d + gap

    listing = DEMO / "_concat.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in padded))
    review = DEMO / "fintor_review.mp4"
    run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(review)])
    rd = duration(review)
    print(f"2. review cut {rd:.2f}s (narration timeline {total:.2f}s "
          f"+ closing hold) -> {review.name}")

    # -- 3. score under the voice ----------------------------------------
    if not SCORE.exists():
        print(f"!  no score at {SCORE}; final = review cut")
        return 0
    close_in = SEGMENTS[-1][1] - 1.5
    env = (f"{MUSIC_GAIN}"
           f"*(1+0.55*exp(-t/6))"                     # lift the open
           f"*(1+0.9*(gte(t,{close_in:.1f})))"        # lift over the close
           f"*min(1,t/2.5)"                           # fade in
           f"*min(1,max(0,({rd:.2f}-t)/3.5))")        # fade out
    final = DEMO / "fintor_final.mp4"
    run([ff, "-y", "-i", str(review), "-i", str(SCORE),
         "-filter_complex",
         f"[1:a]atrim=0:{rd:.3f},asetpts=N/SR/TB,"
         f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
         f"volume='{env}':eval=frame[mus];"
         f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
         f"asplit=2[voice][key];"
         f"[mus][key]sidechaincompress=threshold={DUCK_THRESHOLD}:"
         f"ratio={DUCK_RATIO}:attack=15:release=450:makeup=1[ducked];"
         f"[voice][ducked]amix=inputs=2:normalize=0:dropout_transition=0,"
         f"alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=11[out]",
         "-map", "0:v", "-map", "[out]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "224k", str(final)])
    print(f"3. final mix -> {final}  ({duration(final):.2f}s)")

    for p in padded:
        p.unlink(missing_ok=True)
    listing.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
