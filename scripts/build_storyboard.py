#!/usr/bin/env python3
"""Turn the narration manifest into a visual storyboard and a recorder manifest.

    .venv/bin/python scripts/build_storyboard.py

Every UI event is anchored to a WORD in the generated speech, not to a fraction
of a block. `build/demo/word_timings.json` holds per-word offsets for all 52
clips; a cue names the phrase it fires on, and the absolute time is looked up.
That is what keeps "sign in as Dev" on the screen at the moment it is said
rather than fifty seconds early, which is the defect this rebuild exists to fix.

Cue matching is fuzzy on purpose: the timings come from ASR, which mis-spells
proper nouns ("Maja" for Maya). A cue matches on a distinctive leading token and
falls back to the block start if the phrase is not found - loudly, never
silently.

Output:
  build/demo/storyboard.md            scene-by-scene, for review
  build/demo/production_manifest.json scene list the recorder consumes
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "build" / "demo"

# Elastic slack allowed at a SCENE boundary to absorb page-load variance.
# Inside a scene the gap is fixed; the voice is never re-timed either way.
SCENE_SLACK_MAX = 4.0

# scene id, title, first block, last block, screen, and the cues inside it.
# cue = (block, phrase-to-anchor-on, action)
SCENES: list[dict] = [
    dict(id="s1", title="Persona gallery", blocks=(1, 5),
         screen="Sign-in gate - all six cards in frame, page not scrolled",
         setup="Gate loaded and settled before t=0. No cursor motion for 3s.",
         cues=[
             (1, None,                "Hold. Full gate in frame, cursor parked off the cards."),
             (2, "There are six",     "Confirm all six cards visible in one viewport."),
             (2, "Maja is",           "Cursor to Maya's card."),
             (3, "Dev is",            "Cursor to Dev's card."),
             (3, "Walter is",         "Cursor to Walter's card."),
             (3, "Priya is",          "Cursor to Priya's card."),
             (4, "Aisha holds",       "Cursor to Aisha's card."),
             (4, "Sam is",            "Cursor to Sam's card."),
             (4, "clicking one",      "CLICK Dev's card. Username autofills; password stays masked."),
             (5, "Two of them",       "Cursor traces Dev's then Walter's question line."),
         ]),
    dict(id="s2", title="Sign in as Dev", blocks=(6, 6),
         screen="Gate -> Chat",
         setup="Dev's card already selected by s1. Form pre-filled.",
         cues=[
             (6, None,                "Hold on the sign-in panel."),
             (6, "We will sign",      "CLICK Sign in."),
             (6, "Every answer",      "Chat must be painted and settled by now."),
         ]),
    dict(id="s3", title="Dev's first question", blocks=(7, 12),
         screen="Chat / Dev",
         setup="Signed in as Dev, empty transcript.",
         cues=[
             (7, None,                "Submit Dev's question. Status panel opens."),
             (9, None,                "Steps stream live; 'Answered' collapses when done."),
             (10, None,               "Answer + Sources in frame. Slow scroll to citations."),
             (11, "Underneath",       "Scroll to the data-status chip."),
             (12, "It is all on",     "Open the About Fintor menu. Do NOT navigate."),
         ]),
    dict(id="s4", title="Same question, Walter", blocks=(13, 17),
         screen="Chat -> Gate -> Chat",
         setup="Signed in as Dev with one answer on screen.",
         cues=[
             (13, "We sign out",      "Sign out, click Walter's card, sign in."),
             (14, "We ask Walter",    "Submit the identical question, word for word."),
             (17, None,               "Answer lands. Hold."),
         ]),
    dict(id="s5", title="Fan-out", blocks=(18, 21),
         screen="Chat / Walter",
         setup="Walter signed in, one answer on screen.",
         cues=[
             (18, "one question",     "Submit the dual-intent question (capital gains + index)."),
             (19, None,               "Status panel shows two agents running concurrently."),
             (20, None,               "Merged answer, renumbered citations."),
             (21, "six specialists",  "Open About Fintor -> AI Internals, agent roster card."),
         ]),
    dict(id="s6", title="Portfolio", blocks=(22, 28),
         screen="Portfolio",
         setup="Signed in as Walter.",
         cues=[
             (22, "The portfolio",    "Navigate to Portfolio."),
             (23, None,               "Total, allocation, holdings in the first viewport."),
             (24, None,               "Right rail: diversification, risk vs stated tolerance."),
             (25, "This is a",        "Slow scroll to the correlation matrix."),
             (27, None,               "Hold; cursor on one high-correlation cell."),
             (28, "Market data",      "Navigate to Market."),
         ]),
    dict(id="s7", title="Market", blocks=(29, 34),
         screen="Market",
         setup="Signed in as Walter.",
         cues=[
             (29, None,               "Freshness marker in frame, real state."),
             (30, "Price history",    "Scroll to price history with 20/50d averages."),
             (32, "The largest",      "Scroll to change / drawdown / volatility."),
             (33, "Both series",      "Indexed-to-100 benchmark comparison in frame."),
         ]),
    dict(id="s8", title="Goals", blocks=(35, 40),
         screen="Goals",
         setup="Signed in as Walter.",
         cues=[
             (35, None,               "Navigate to Goals (1.5s early so it is painted on the word)."),
             (36, "The dashed",       "Dashed target line in frame."),
             (38, "Underneath",       "Scroll to the +/-2pp sensitivity table."),
             (40, "And the",          "Scroll to the assumptions list."),
         ]),
    dict(id="s9", title="AI Internals", blocks=(41, 48),
         screen="AI Internals",
         setup="Re-ask Dev's question first so a cache hit is on record (G5).",
         cues=[
             (41, None,               "Navigate to AI Internals. Routing decision card in frame."),
             (42, "The persona",      "Scroll to persona conditioning, then graph trace."),
             (43, "Every candidate",  "Scroll to retrieval candidates (dense, BM25, fused)."),
             (46, "Every model",      "Scroll to model calls - the zero-cost cache hit row."),
             (47, None,               "Hold on the three cache stores."),
             (48, "The first",        "Show the Langfuse link (do not click), then Architecture."),
         ]),
    dict(id="s10", title="Specs, governance, MCP", blocks=(49, 51),
         screen="Architecture -> Design Document -> Governance + terminal inset",
         setup="Terminal inset recorded separately, composited.",
         cues=[
             (49, "Behind it",        "Step through Design Document, then Governance matrix."),
             (50, "The same",         "Terminal inset: python -m src.mcp_server listing its six tools."),
             (51, "One implementation", "Back to full frame; coverage and offline-test evidence."),
         ]),
    dict(id="s11", title="Close", blocks=(52, 52),
         screen="Animated closing card",
         setup="Rendered, not recorded from the browser.",
         cues=[
             (52, "Fintor",           "Logo + wordmark reveal."),
             (52, "finance",          "Type 'Finance, made approachable.' in sync."),
         ]),
]


def load() -> tuple[dict, dict]:
    man = json.loads((DEMO / "narration_manifest.json").read_text())
    words = json.loads((DEMO / "word_timings.json").read_text())
    return {b["block"]: b for b in man["blocks"]}, words


def resolve(blocks: dict, words: dict, block: int, phrase: str | None) -> tuple[float, bool]:
    """Absolute start time of `phrase` inside `block`. (time, matched)."""
    start = blocks[block]["speech_in"]
    if phrase is None:
        return start, True
    ws = words[str(block)]
    norm = [re.sub(r"[^a-z0-9]", "", w["w"].lower()) for w in ws]
    toks = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in phrase.split()]
    for i in range(len(norm) - len(toks) + 1):
        if norm[i:i + len(toks)] == toks:
            return round(start + ws[i]["s"], 2), True
    return start, False


def main() -> int:
    blocks, words = load()
    unmatched, out_scenes = [], []
    md = ["# Fintor demo - visual storyboard",
          "",
          "Generated by `scripts/build_storyboard.py` from the narration manifest and "
          "per-word speech timings. Every timestamp below is the moment the anchoring "
          "phrase is **actually spoken**, measured from the rendered audio.",
          ""]

    for sc in SCENES:
        b0, b1 = sc["blocks"]
        t_in = blocks[b0]["speech_in"]
        t_out = blocks[b1]["speech_out"]
        cues = []
        for block, phrase, action in sc["cues"]:
            t, ok = resolve(blocks, words, block, phrase)
            if not ok:
                unmatched.append((sc["id"], block, phrase))
            cues.append({"at": t, "block": block, "anchor": phrase,
                         "action": action, "anchored": ok})
        out_scenes.append({"id": sc["id"], "title": sc["title"],
                           "blocks": [b0, b1], "screen": sc["screen"],
                           "setup": sc["setup"],
                           "in": round(t_in, 2), "out": round(t_out, 2),
                           "duration": round(t_out - t_in, 2),
                           "slack_max": SCENE_SLACK_MAX, "cues": cues})

        md += [f"## {sc['id'].upper()} - {sc['title']}", "",
               f"**{t_in:.2f}s to {t_out:.2f}s** ({t_out - t_in:.2f}s) · "
               f"blocks {b0}-{b1} · {sc['screen']}", "",
               f"*Setup:* {sc['setup']}", "",
               "| at | block | spoken anchor | action |", "|---|---|---|---|"]
        for c in cues:
            anchor = f"`{c['anchor']}`" if c["anchor"] else "_block start_"
            flag = "" if c["anchored"] else " **(UNANCHORED)**"
            md.append(f"| {c['at']:.2f} | {c['block']} | {anchor}{flag} | {c['action']} |")
        md.append("")

    (DEMO / "storyboard.md").write_text("\n".join(md), encoding="utf-8")
    (DEMO / "production_manifest.json").write_text(json.dumps({
        "total_seconds": round(max(s["out"] for s in out_scenes), 2),
        "scene_slack_max": SCENE_SLACK_MAX,
        "scenes": out_scenes}, indent=2) + "\n", encoding="utf-8")

    print(f"{len(out_scenes)} scenes | "
          f"{sum(len(s['cues']) for s in out_scenes)} cues | "
          f"{len(unmatched)} unanchored")
    for sid, b, p in unmatched:
        print(f"  UNANCHORED {sid} b{b}: {p!r} -> fell back to block start")
    return 0


if __name__ == "__main__":
    sys.exit(main())
