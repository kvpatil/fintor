#!/usr/bin/env python3
"""Re-mix the score under the finished narration. Audio only.

    .venv/bin/python scripts/remix.py              # full mix + 30s preview
    .venv/bin/python scripts/remix.py --preview    # preview only

Reads the narration-only stem `fintor_review.mp4` and the score, and writes
`fintor_final_v2.mp4`. The video stream is COPIED, never re-encoded, so the
approved picture is bit-identical. The approved `fintor_final.mp4` is left
alone until the new mix is signed off.

WHAT CHANGED FROM THE FIRST MIX, and why - each of these was measured on the
rendered file, not guessed:

* The sidechain threshold was 0.02 (-34 dBFS), BELOW the voice's own RMS, at
  ratio 9. So the compressor was fully engaged on every syllable and the
  music's contribution under speech measured -120 dB - silence. Now 0.06
  (-24 dBFS) at ratio 3.5: it dips on loud syllables and no further.
* Release was 450ms against inter-block gaps of 450ms, so the music could
  never recover inside a gap. Now 220ms.
* `loudnorm` ran on the SUMMED signal, which normalises to the voice and
  flattens what is left of the music. Now the voice stem is normalised on its
  own before the mix, and the sum gets a static trim plus a limiter - a fixed
  gain cannot squash dynamics.
* The score is a flat bed: it measures -20.5 to -22.6 dB across 30s windows
  for its entire 9:21, a 2dB spread. There is no arc in the file to uncover,
  so the progression below is authored.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "build" / "demo"
STEM = DEMO / "fintor_review.mp4"
SCORE = Path.home() / "Documents/IK-FDE/elevenlabs/fintor_cinematic_score.mp3"
OUT = DEMO / "fintor_final_v2.mp4"
PREVIEW = DEMO / "fintor_mix_preview.mp4"
MUSIC_STEM = DEMO / "_music_stem.wav"

VOICE_LUFS = -17.0        # the voice stem, normalised alone

# Music gain relative to the score's own level (it measures -21.7 dB RMS), so
# these land near the absolute targets the mix report checks.
#
# AUTHORED, NOT TRIGGERED. A sidechain compressor was tried first and is the
# wrong tool here: with a release short enough to recover inside a 450ms
# inter-block gap, the music rebounds between every word, so its level across
# a spoken block barely moves - ratio 3.5 -> 9.0 shifted it 0.5 dB. The block
# boundaries are known exactly from narration_manifest.json, so the ducking is
# written as automation against them instead. Deterministic, and it is what a
# dub mixer would actually do.
# Calibrated against mix_report.py, not chosen by ear. The chain is linear in
# dB, so one measure-and-correct pass converges: these are the previous values
# plus the gap between what was measured and the target.
UNDER_SPEECH_DB = -4.5    # start of the build; rises to about -30 dB
IN_GAP_DB = 2.9           # start of the build; rises to about -17 dB

# The build is weighted towards the GAPS, not through the dialogue. With one
# arc applied equally to both states the spread under speech came out at
# 1.8 dB across the whole middle - inaudible - and widening it would have cut
# into the 11 dB of separation the voice needs. In the spaces between blocks
# there is no voice to protect, so that is where the section-to-section lift
# can actually be heard.
SPEECH_ARC_SCALE = 0.7    # keeps >=9 dB of separation at the loudest section
GAP_ARC_SCALE = 2.0
OVER_CLOSE_DB = 7.7       # -> about -14 dB
SMOOTH_MS = 220           # fade between the two states, both directions
DUCK_THRESHOLD = 0.06     # safety net only; the automation does the work
# Ratio, not threshold, is the knob here. At 3.5 the music sat 6.7 dB under
# the voice - measured, and too close for consonants. Dropping the THRESHOLD
# instead would recreate the original fault (always-on compression); raising
# the ratio deepens the dip only while speech is actually above -24 dBFS.
DUCK_RATIO = 2.0
PROGRAMME_LUFS = -16.0
TRUE_PEAK = -1.5
# alimiter clamps SAMPLE peak; true (inter-sample) peak runs about 1 dB
# hotter, which is how a -1.5 ceiling measured -0.0 dBTP. Ceiling the limiter
# a dB lower than the true-peak target and verify the measured value.
LIMITER_CEILING = -2.5

# (boundary seconds, dB added from there on, ramp seconds). Boundaries are the
# scene-group edges already in production_manifest.json.
ARC = [(228.02, 1.5, 6.0),     # demonstration II - portfolio, market, goals
       (434.85, 1.5, 6.0),     # technical - internals, specs, MCP
       (556.10, 7.0, 1.2)]     # the close

# The tail fade must be SHORT. At 3.0s it began at 558.96s and reached zero at
# the end - straight through the closing hold, which is the one stretch with no
# narration and the place the score is supposed to resolve. Measured at -19.7 dB
# against a -14 dB target before this was cut to 1.2s.
TAIL_FADE = 1.2

PREVIEW_WINDOWS = [(0.0, 10.0), (440.0, 450.0), (551.97, 561.97)]


def ff() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(cmd: list[str], stdin: bytes | None = None) -> str:
    r = subprocess.run(cmd, capture_output=True, input=stdin)
    if r.returncode:
        print(r.stderr.decode(errors="replace")[-2500:])
        raise SystemExit("ffmpeg failed")
    return r.stderr.decode(errors="replace")


def duration(p: Path) -> float:
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)",
                  subprocess.run([ff(), "-i", str(p)], capture_output=True,
                                 text=True).stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def envelope(dur: float) -> str:
    """Music gain in dB over time, as an ffmpeg frame-evaluated expression."""
    terms = [f"{MUSIC_BASE_DB}"]
    for at, lift, ramp in ARC:
        terms.append(f"{lift}*clip((t-{at})/{ramp},0,1)")
    gain_db = "+".join(terms)
    fade_in = "clip(t/3.5,0,1)"
    fade_out = f"clip(({dur:.2f}-t)/{TAIL_FADE},0,1)"
    return f"pow(10,({gain_db})/20)*{fade_in}*{fade_out}"


def build_music(dur: float) -> Path:
    """Render the automated music bed to a WAV, ready to sum with the voice.

    The gain curve is derived from the narration manifest: down while a block
    is speaking, up in the gaps between them, up again over the closing hold,
    with the section arc on top. Smoothed with a raised-cosine window so the
    transitions are fades rather than steps.
    """
    import numpy as np
    sr = 48000
    raw = subprocess.run([ff(), "-i", str(SCORE), "-ac", "2", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)
    n = int(dur * sr)
    if len(a) < n:                      # loop if the score is short
        a = np.tile(a, (n // len(a) + 1, 1))
    a = a[:n].copy()

    blocks = json.loads((DEMO / "narration_manifest.json").read_text())["blocks"]
    t = np.arange(n, dtype=np.float32) / sr

    speaking = np.zeros(n, dtype=bool)
    for b in blocks:
        i0, i1 = int(b["speech_in"] * sr), min(int(b["speech_out"] * sr), n)
        speaking[i0:i1] = True

    arc = np.zeros(n, dtype=np.float32)
    for at, lift, ramp in ARC[:-1]:               # the close is handled below
        arc += lift * np.clip((t - at) / ramp, 0, 1)

    gain = np.where(speaking,
                    UNDER_SPEECH_DB + arc * SPEECH_ARC_SCALE,
                    IN_GAP_DB + arc * GAP_ARC_SCALE).astype(np.float32)

    close_at = ARC[-1][0]
    after = t >= close_at
    gain[after] = OVER_CLOSE_DB

    win = max(1, int(SMOOTH_MS / 1000 * sr))
    k = np.hanning(win * 2 + 1).astype(np.float32)
    k /= k.sum()
    gain = np.convolve(np.pad(gain, win, mode="edge"), k, mode="same")[win:-win]

    lin = (10 ** (gain / 20)).astype(np.float32)
    lin *= np.clip(t / 3.5, 0, 1)                              # head fade
    lin *= np.clip((dur - t) / TAIL_FADE, 0, 1)                # tail fade
    a *= lin[:, None]

    dest = DEMO / "_music_bed.wav"
    pcm = np.clip(a, -1, 1)
    run([ff(), "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2",
         "-i", "pipe:0", "-c:a", "pcm_s16le", str(dest)],
        stdin=pcm.astype(np.float32).tobytes())
    print(f"          music bed: speech {UNDER_SPEECH_DB:+.1f} dB, "
          f"gap {IN_GAP_DB:+.1f} dB, close {OVER_CLOSE_DB:+.1f} dB")
    return dest


def chain(dur: float, trim_db: float) -> str:
    return (
        f"[1:a]atrim=0:{dur:.3f},asetpts=N/SR/TB,"
        f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        # Carve a shallow notch where consonants live so the bed can sit
        # louder without eating intelligibility.
        f"equalizer=f=2000:t=q:w=1.0:g=-3[mus];"
        f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        # apad+atrim after loudnorm is NOT cosmetic. loudnorm's dynamic mode
        # runs a lookahead buffer and returns a stream SHORTER than its input -
        # measured 559.62s against 561.96s. That truncated voice then became
        # the sidechain key, which truncated the music with it, and the score
        # simply stopped 2.3s before the end: straight through the closing
        # resolution, which is the one place it is supposed to be loudest.
        f"loudnorm=I={VOICE_LUFS}:TP=-2.0:LRA=11,"
        f"apad=whole_dur={dur:.3f},atrim=0:{dur:.3f},asetpts=N/SR/TB,"
        f"asplit=2[voice][key];"
        f"[mus][key]sidechaincompress=threshold={DUCK_THRESHOLD}:"
        f"ratio={DUCK_RATIO}:attack=20:release=220:makeup=1[duck];"
        f"[voice][duck]amix=inputs=2:normalize=0:dropout_transition=0,"
        f"volume={trim_db:.2f}dB,"
        f"alimiter=limit={10 ** (TRUE_PEAK / 20):.4f}[out]")


def measure(path: Path) -> tuple[float, float]:
    """(integrated LUFS, true peak dBTP) of a rendered file."""
    err = run([ff(), "-i", str(path), "-af",
               f"loudnorm=I={PROGRAMME_LUFS}:TP={TRUE_PEAK}:LRA=11:"
               "print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", err, re.S)
    if not m:
        return 0.0, 0.0
    d = json.loads(m.group(0))
    return float(d["input_i"]), float(d["input_tp"])


def measure_lufs(path: Path) -> float:
    err = run([ff(), "-i", str(path), "-af",
               f"loudnorm=I={PROGRAMME_LUFS}:TP={TRUE_PEAK}:LRA=11:"
               "print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", err, re.S)
    return float(json.loads(m.group(0))["input_i"]) if m else 0.0


def render(dur: float, trim_db: float, dest: Path, bed: Path) -> None:
    run([ff(), "-y", "-i", str(STEM), "-i", str(bed),
         "-filter_complex", chain(dur, trim_db),
         "-map", "0:v", "-map", "[out]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "224k", str(dest)])


def render_music_stem(dur: float, trim_db: float, dest: Path, bed: Path) -> None:
    """The ducked music ALONE, through the identical chain.

    Needed because the music level under speech cannot be recovered from the
    mix by subtracting the stem: loudnorm on the voice is a dynamic process,
    so the voice in the mix is not a scaled copy of the voice in the stem and
    the subtraction collapses (it reported -103 dB, i.e. perfect
    cancellation). The voice still drives the sidechain here - it is simply
    not summed into the output - so this is the real ducked music, measurable
    directly.
    """
    run([ff(), "-y", "-i", str(STEM), "-i", str(bed),
         "-filter_complex",
         chain(dur, trim_db).replace(
             "[voice][duck]amix=inputs=2:normalize=0:dropout_transition=0,",
             "[voice]anullsink;[duck]"),
         "-map", "[out]", "-c:a", "pcm_s16le", str(dest)])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preview", action="store_true",
                    help="cut the preview from an existing v2 mix")
    args = ap.parse_args()

    if not STEM.exists():
        raise SystemExit(f"missing narration stem {STEM}")
    if not SCORE.exists():
        raise SystemExit(f"missing score {SCORE}")
    dur = duration(STEM)

    if not args.preview:
        # Pass 1 at unity trim, measure, then a STATIC correction. A static
        # gain moves the level without touching the dynamics, which is the
        # whole reason loudnorm is no longer on the sum.
        print(f"pass 1/2  mixing {dur:.2f}s at trim 0 dB")
        bed = build_music(dur)
        render(dur, 0.0, OUT, bed)
        got = measure_lufs(OUT)
        trim = PROGRAMME_LUFS - got
        print(f"          measured {got:.2f} LUFS -> trim {trim:+.2f} dB")
        if abs(trim) > 0.15:
            print("pass 2/2  re-rendering with the trim applied")
            render(dur, trim, OUT, bed)
            print(f"          now {measure_lufs(OUT):.2f} LUFS")
        else:
            trim = 0.0

        # Pass 3: true peak. alimiter clamps SAMPLE peak, and AAC encoding
        # overshoots on top of that, so a -2.5 dBFS ceiling still measured
        # -0.3 dBTP. A static trim is the honest correction - it moves the
        # whole programme down without touching the balance that passes 1-2
        # established.
        lufs, tp = measure(OUT)
        if tp > TRUE_PEAK:
            trim += TRUE_PEAK - tp - 0.1
            print(f"pass 3/3  true peak {tp:+.2f} dBTP over {TRUE_PEAK} "
                  f"-> trim {trim:+.2f} dB")
            render(dur, trim, OUT, bed)
            lufs, tp = measure(OUT)
        print(f"          {lufs:.2f} LUFS, true peak {tp:+.2f} dBTP")
        render_music_stem(dur, trim, MUSIC_STEM, bed)
        print(f"wrote {OUT}\n      {MUSIC_STEM.name} (ducked music alone, for measurement)")

    # 30s preview: three windows cut from the REAL mix, hard joined.
    parts = []
    for i, (s, e) in enumerate(PREVIEW_WINDOWS):
        p = DEMO / f"_prev{i}.mp4"
        run([ff(), "-y", "-ss", f"{s:.3f}", "-i", str(OUT), "-t", f"{e - s:.3f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "224k", str(p)])
        parts.append(p)
    listing = DEMO / "_prev.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    run([ff(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", str(PREVIEW)])
    for p in parts:
        p.unlink(missing_ok=True)
    listing.unlink(missing_ok=True)
    print(f"preview {duration(PREVIEW):.2f}s -> {PREVIEW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
