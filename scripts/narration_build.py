#!/usr/bin/env python3
"""Build Fintor's narration track from the approved transcript.

    .venv/bin/python scripts/narration_build.py

Reads the approved `narration_review.txt`, applies the audited corrections in
CORRECTIONS below, and synthesises ONLY the blocks whose text changed. Every
other block is served from the existing ElevenLabs cache, byte for byte - the
cache key is a hash of (text, voice, model, speed), so an unchanged line can
never be silently re-cut.

The nine corrections are transcription defects in the approved script, each one
checked against the implementation rather than against intuition:

  b4   Asha            -> Aisha              src/data/personas.py:82
  b5   script          -> scrypt             src/core/auth.py (hashlib.scrypt)
  b13  For years       -> Four years         personas.py:64 horizon_years=4
  b21  One's           -> Finance            Intent.FINANCE_QA
  b26  And does not    -> Diversification    (sentence had no subject)
  b44  And search      -> Keyword search     src/rag - BM25 leg of the fusion
       parent phrases  -> paraphrases
  b46  cash tier       -> cache tier         internals.py CACHE_NOTE column
  b47  cash            -> cache              three stores: llm.db, embeddings.db,
       never built     -> never billed       market.db (container.py:84-91)
  b50  cloud desktop   -> Claude Desktop     src/mcp_server/server.py:225

Output:
  build/demo/narration_final.txt      corrected transcript, same block order
  build/demo/narration_manifest.json  per-block clip path, duration, in/out
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ELEVEN = Path(os.environ.get("FINTOR_ELEVENLABS_DIR",
                             Path.home() / "Documents/IK-FDE/elevenlabs"))
CACHE = ELEVEN / ".narration_cache"
SOURCE = ELEVEN / "narration_review.txt"
OUT_DIR = REPO / "build" / "demo"

VOICE = "JBFqnCBsd6RMkjVDRZzb"
MODEL = "eleven_multilingual_v2"
SPEED = 0.95          # the agreed natural pacing. Never raised to fit a cut.
PAUSE = 0.45          # inter-block gap inside a scene

# (block number, exact substring, replacement). Substring rather than regex so a
# correction that stops matching fails loudly instead of silently doing nothing.
CORRECTIONS: list[tuple[int, str, str]] = [
    (4,  "Asha holds crypto.",            "Aisha holds crypto."),
    (5,  "hashed with script",            "hashed with scrypt"),
    (13, "For years from retiring",       "Four years from retiring"),
    (21, "One's question answering",      "Finance question answering"),
    (26, "And does not come from owning", "Diversification does not come from owning"),
    (44, "And search alone misses parent phrases",
         "Keyword search alone misses paraphrases"),
    (46, "which cash tier served it",     "which cache tier served it"),
    (47, "an exact match cash for completions",
         "an exact-match cache for completions"),
    (47, "an offline mode that is never built at all",
         "an offline mode that is never billed at all"),
    (50, "another agent, cloud desktop,", "another agent, Claude Desktop,"),
]

# Written spelling -> spelling fed to the TTS, where the two differ.
# "scrypt" is read aloud as "script" by this voice - verified by synthesising
# both spellings and transcribing the result - which is the exact confusion the
# b5 correction exists to remove. "S-crypt" is read as "ess-crypt". The written
# transcript keeps the real term; only the API input is respelled.
SPEECH_SPELLING: dict[str, str] = {"scrypt": "S-crypt"}

LINE = re.compile(r"^\s*\[\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*s\s*\]\s*(.*?)\s*$")


def spoken(text: str) -> str:
    """What is actually sent to ElevenLabs - and therefore what keys the cache."""
    for written, said in SPEECH_SPELLING.items():
        text = text.replace(written, said)
    return text


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    out = subprocess.run([ffmpeg(), "-i", str(path)],
                         capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out)
    if not m:
        raise RuntimeError(f"no duration for {path}")
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def cache_path(text: str) -> Path:
    params = json.dumps([spoken(text), VOICE, MODEL, SPEED], ensure_ascii=False)
    return CACHE / f"{hashlib.sha256(params.encode()).hexdigest()[:24]}.mp3"


def read_blocks() -> list[str]:
    blocks = []
    for line in SOURCE.read_text(encoding="utf-8-sig").splitlines():
        m = LINE.match(line)
        if m:
            blocks.append(m[3])
    return blocks


def apply_corrections(blocks: list[str]) -> tuple[list[str], set[int]]:
    out, touched = list(blocks), set()
    for n, old, new in CORRECTIONS:
        i = n - 1
        if old not in out[i]:
            raise SystemExit(
                f"correction {n} no longer matches - the transcript changed.\n"
                f"  looking for: {old!r}\n  in block {n}: {out[i]!r}")
        out[i] = out[i].replace(old, new)
        touched.add(n)
    return out, touched


def load_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key
    envfile = ELEVEN / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    raise SystemExit("no ELEVENLABS_API_KEY (env or elevenlabs/.env)")


def synth(client, dest: Path, text: str) -> None:
    from elevenlabs import VoiceSettings
    stream = client.text_to_speech.convert(
        text=spoken(text), voice_id=VOICE, model_id=MODEL,
        output_format="mp3_44100_128",
        voice_settings=VoiceSettings(stability=0.42, similarity_boost=0.75,
                                     style=0.08, speed=SPEED))
    part = dest.with_suffix(".part")
    with part.open("wb") as f:
        for chunk in stream:
            if chunk:
                f.write(chunk)
    if part.stat().st_size == 0:
        raise RuntimeError("ElevenLabs returned empty audio")
    part.replace(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be synthesised; call no API")
    args = ap.parse_args()

    original = read_blocks()
    if len(original) != 52:
        raise SystemExit(f"expected 52 blocks, found {len(original)}")
    corrected, touched = apply_corrections(original)

    missing = [(i + 1, t) for i, t in enumerate(corrected)
               if not cache_path(t).exists()]
    print(f"{len(corrected)} blocks | corrected: {sorted(touched)} | "
          f"to synthesise: {[n for n, _ in missing]}")
    for n, _ in missing:
        if n not in touched:
            raise SystemExit(f"block {n} is uncorrected but has no cached clip - "
                             f"refusing to re-cut approved narration")
    if args.dry_run:
        return 0

    if missing:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=load_key())
        for n, text in missing:
            dest = cache_path(text)
            print(f"  synth b{n:02d} -> {dest.name}", flush=True)
            synth(client, dest, text)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows, t = [], 0.0
    for i, text in enumerate(corrected, 1):
        clip = cache_path(text)
        d = duration(clip)
        rows.append({"block": i, "text": text, "clip": str(clip),
                     "corrected": i in touched,
                     "speech_in": round(t, 3), "speech_out": round(t + d, 3),
                     "duration": round(d, 3)})
        t += d + PAUSE
    total = t - PAUSE

    (OUT_DIR / "narration_final.txt").write_text(
        "\n".join(f"[{r['speech_in']:.1f}–{r['speech_out']:.1f}s] {r['text']}"
                  for r in rows) + "\n", encoding="utf-8")
    (OUT_DIR / "narration_manifest.json").write_text(json.dumps({
        "voice": VOICE, "model": MODEL, "speed": SPEED, "pause": PAUSE,
        "speech_seconds": round(sum(r["duration"] for r in rows), 3),
        "total_seconds": round(total, 3),
        "blocks": rows}, indent=2) + "\n", encoding="utf-8")

    print(f"speech {sum(r['duration'] for r in rows):.2f}s | "
          f"timeline {total:.2f}s | wrote {OUT_DIR}/narration_manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
