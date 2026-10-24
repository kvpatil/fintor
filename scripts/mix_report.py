#!/usr/bin/env python3
"""Measure the music/voice balance of a mix against explicit targets.

    .venv/bin/python scripts/mix_report.py build/demo/fintor_final_v2.mp4

The narration-only stem (`fintor_review.mp4`) is digital silence between
blocks, so any energy in those gaps in the mixed file IS the music - that is
what makes the balance measurable rather than a matter of opinion.

Reports four numbers and the loudness, against the targets agreed for this
mix. Written because the previous mix was shipped on "the score is in there":
it was, at -26 dB in the 3% of the runtime that is not speech, and inaudible
under the other 97%.
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
SR = 8000

# (name, target dB, tolerance)
TARGETS = {
    "music under speech": (-30.0, 3.0),
    "music in gaps": (-20.0, 3.0),
    "music over close": (-14.0, 3.0),
}


def ff() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def mono(path: Path, sr: int = SR) -> np.ndarray:
    r = subprocess.run([ff(), "-i", str(path), "-ac", "1", "-ar", str(sr),
                        "-f", "s16le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def db(x) -> float:
    x = np.asarray(x)
    if x.size == 0:
        return -99.0
    return 20 * np.log10(max(float(np.sqrt((x ** 2).mean())), 1e-9))


def take(sig, spans) -> np.ndarray:
    out = [sig[int(s * SR):int(e * SR)] for s, e in spans
           if int(e * SR) <= len(sig) and e > s]
    out = [c for c in out if c.size]
    return np.concatenate(out) if out else np.zeros(1, dtype=np.float32)


def loudness(p: Path) -> tuple[float, float]:
    r = subprocess.run([ff(), "-i", str(p), "-af",
                        "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", r.stderr, re.S)
    if not m:
        return 0.0, 0.0
    d = json.loads(m.group(0))
    return float(d["input_i"]), float(d["input_tp"])


def main() -> int:
    mix = Path(sys.argv[1] if len(sys.argv) > 1 else DEMO / "fintor_final.mp4")
    stem = DEMO / "fintor_review.mp4"
    man = json.loads((DEMO / "narration_manifest.json").read_text())
    blocks = man["blocks"]

    a, v = mono(mix), mono(stem)
    gaps = [(x["speech_out"] + 0.10, y["speech_in"] - 0.06)
            for x, y in zip(blocks, blocks[1:])
            if y["speech_in"] - x["speech_out"] > 0.21]
    speech = [(b["speech_in"] + 0.30, b["speech_out"] - 0.30)
              for b in blocks if b["duration"] > 1.0]
    close = [(blocks[-1]["speech_out"] + 0.4, blocks[-1]["speech_out"] + 3.0)]

    voice_lvl = db(take(a, speech))

    # Music under speech is measured on the ducked-music stem that remix.py
    # writes, NOT inferred from the mix. Subtracting the narration stem does
    # not work: loudnorm on the voice is dynamic, so the mixed voice is not a
    # scaled copy of the stem and the residual cancels to nonsense (-103 dB).
    stem_wav = DEMO / "_music_stem.wav"
    if stem_wav.exists():
        m = mono(stem_wav)
        under, src = db(take(m, speech)), "measured"
    else:
        under, src = float("nan"), "NO STEM - run remix.py"

    vals = {"music under speech": under,
            "music in gaps": db(take(a, gaps)),
            "music over close": db(take(a, close))}
    print(f"\n  (music-under-speech read from {src})", end="")
    i_lufs, tp = loudness(mix)

    print(f"\nMix report — {mix.name}")
    print("=" * 66)
    print(f"  {'voice during speech':<22} {voice_lvl:7.1f} dB   (reference)")
    fails = 0
    for k, got in vals.items():
        tgt, tol = TARGETS[k]
        ok = abs(got - tgt) <= tol
        fails += 0 if ok else 1
        print(f"  {k:<22} {got:7.1f} dB   target {tgt:+.0f}±{tol:.0f}   "
              f"{'ok' if ok else 'OUT'}")
    sep = voice_lvl - under
    print(f"  {'voice over music':<22} {sep:7.1f} dB   "
          f"({'clear' if sep >= 8 else 'TOO CLOSE'})")
    print(f"  {'programme loudness':<22} {i_lufs:7.1f} LUFS  peak {tp:.1f} dBTP")
    print("=" * 66)
    print(f"  {len(vals) - fails}/{len(vals)} level targets met\n")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
