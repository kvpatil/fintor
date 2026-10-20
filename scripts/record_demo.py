"""Record the demo walkthrough as silent video, paced to the narration.

Run the app first, then:

    FINTOR_DEMO_PASSWORD=<something> .venv/bin/streamlit run src/web_app/app.py &
    .venv/bin/python scripts/record_demo.py --password <same>

WHY THE AUDIO IS RENDERED FIRST
-------------------------------
The obvious order - film it, then talk over it - desynchronises, because
Streamlit rerun times are not constant between takes. So the narration is
rendered up front with `say`, each clip is measured, and the browser is then
driven against those measurements: perform the beat's actions, then wait until
that beat's audio duration has elapsed. The footage is built to fit the audio
rather than stretched to match it afterwards.

A beat that overruns its narration is fine - it reads as a pause. A beat that
finishes early would read as desync, which is why every beat pads rather than
racing ahead.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Imported, not restated. See chat.py: duplicating this string is what broke
# the recorder when the label was reworded.
from src.web_app.views.chat import DONE_LABEL  # noqa: E402
BUILD = ROOT / "build" / "demo"
AUDIO = BUILD / "audio"
VIDEO = BUILD / "video"
NARRATION = ROOT / "scripts" / "narration.toml"

# 1600x900 keeps the 1280px content measure comfortably inside the frame with
# margin either side, and downscales cleanly to 720p if the file needs to be
# smaller for upload.
VIEWPORT = {"width": 1600, "height": 900}

APP_URL = "http://localhost:8501"


@dataclass
class Beat:
    id: str
    text: str
    pause_after: float
    seconds: float = 0.0   # filled in once the clip is measured


# --- narration ----------------------------------------------------------


def load_beats() -> tuple[list[Beat], str, int]:
    spec = tomllib.loads(NARRATION.read_text(encoding="utf-8"))
    beats = [
        Beat(id=b["id"], text=" ".join(b["text"].split()),
             pause_after=float(b.get("pause_after", 0.0)))
        for b in spec["beat"]
    ]
    return beats, spec.get("voice", "Alex"), int(spec.get("rate", 185))


def render_audio(beats: list[Beat], voice: str, rate: int) -> None:
    """`say` each beat to its own clip, then measure it.

    Measured rather than estimated from a words-per-minute guess: `say` does not
    hit its nominal rate exactly, and the error compounds across nine beats.
    """
    AUDIO.mkdir(parents=True, exist_ok=True)
    for i, beat in enumerate(beats, 1):
        out = AUDIO / f"{i:02d}-{beat.id}.aiff"
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(out), beat.text],
                       check=True)
        beat.seconds = probe_seconds(out)
        words = len(beat.text.split())
        print(f"  {beat.id:16} {beat.seconds:6.1f}s  {words:4d} words")


def probe_seconds(path: Path) -> float:
    """Duration in seconds. afinfo ships with macOS; ffprobe is the fallback."""
    if shutil.which("afinfo"):
        out = subprocess.run(["afinfo", str(path)], capture_output=True, text=True).stdout
        for line in out.splitlines():
            if "estimated duration" in line:
                return float(line.split(":")[1].strip().split()[0])
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# --- the walkthrough ----------------------------------------------------


def sign_in(page, username: str, password: str) -> None:
    page.wait_for_selector('[data-testid="stTextInput"] input', timeout=30_000)
    boxes = page.locator('[data-testid="stTextInput"] input')
    boxes.nth(0).fill(username)
    boxes.nth(1).fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_selector('[data-testid="stTopNavLink"]', timeout=60_000)


def ask(page, question: str, settle_ms: int = 120_000) -> None:
    """Type a question and wait for THIS turn's workflow to finish.

    Counting the completion markers rather than waiting for one to exist: the status
    widget from the previous turn stays collapsed in the DOM still reading
    complete, so a plain wait_for_selector returns instantly on every question
    after the first, and the recorder would race ahead of the answer.
    """
    import time

    before_done = page.get_by_text(DONE_LABEL, exact=True).count()
    before_msgs = page.locator('[data-testid="stChatMessage"]').count()

    box = page.locator('[data-testid="stChatInputTextArea"]')
    box.fill(question)
    box.press("Enter")

    # WALL CLOCK, not a decrementing counter. The previous version subtracted
    # `step` per iteration while ignoring how long the DOM query itself took -
    # and get_by_text().count() grows slow as the transcript grows. A nominal
    # 120s budget actually ran 250s on a long thread, which the mux then had
    # to squeeze into a 50s narration slot: a 5x fast-forward in the cut.
    deadline = time.monotonic() + settle_ms / 1000
    while time.monotonic() < deadline:
        page.wait_for_timeout(750)
        # Either signal is enough. The status label is the precise one; the
        # message count is the one that still works if the label is reworded
        # or the status widget collapses out of the text layer.
        if (page.get_by_text(DONE_LABEL, exact=True).count() > before_done
                or page.locator('[data-testid="stChatMessage"]').count() >= before_msgs + 2):
            break
    else:
        print(f"    ! no answer within {settle_ms / 1000:.0f}s for: {question[:48]}")
    page.wait_for_timeout(2000)


def nav(page, label: str) -> None:
    page.get_by_role("link", name=label).first.click()
    page.wait_for_timeout(2500)


def scroll_through(page, steps: int = 4, dwell: int = 900) -> None:
    """Ease down the page so the viewer can read, rather than jumping."""
    for _ in range(steps):
        page.mouse.wheel(0, 420)
        page.wait_for_timeout(dwell)


def open_about(page, item: str) -> None:
    """Open an About Fintor page through its dropdown.

    "About Fintor" is a stTopNavSection, NOT a nav link - get_by_role("link")
    does not match it, which is what killed the first full take on the very
    last beat. Navigating straight to /architecture is not an alternative
    either: a fresh URL is a fresh Streamlit session, so it lands back on the
    sign-in screen.
    """
    section = page.locator('[data-testid="stTopNavSection"]')
    if section.count():
        section.first.click()
    else:
        page.get_by_text("About Fintor", exact=False).first.click()
    page.wait_for_timeout(1500)

    for attempt in (
        lambda: page.get_by_role("link", name=item).first.click(timeout=4000),
        lambda: page.get_by_text(item, exact=True).first.click(timeout=4000),
        lambda: page.locator(f'[data-testid="stTopNavLink"]:has-text("{item}")')
                    .first.click(timeout=4000),
    ):
        try:
            attempt()
            page.wait_for_timeout(2500)
            return
        except Exception:
            continue
    print(f"    ! could not open About Fintor > {item}")


def walk(page, beats: list[Beat], password: str) -> list[dict]:
    """Run each beat, padded to its narration, and report what actually happened.

    Returns a span per beat: when it started and ended in the recording's own
    timeline. The mux needs this because a beat can overrun - the fan-out
    question went 74.5s past its budget on one take - and a single uniform
    re-time cannot repair a localised overrun, it only shifts everything after
    it. With real spans, each segment is fitted to its own narration clip.
    """
    import time

    def pace(beat: Beat, started: float) -> None:
        target = beat.seconds + beat.pause_after
        spent = time.monotonic() - started
        remaining = target - spent
        if remaining > 0:
            page.wait_for_timeout(int(remaining * 1000))
        else:
            print(f"    ! {beat.id} ran {abs(remaining):.1f}s over its narration")

    # A beat that throws must not destroy the take. The first full run died on
    # the last beat's selector after eight good beats and nine minutes of live
    # model calls, and threw the footage away with it. Now a failed beat is
    # logged, padded to its slot so the narration stays aligned, and the run
    # continues.
    spans: list[dict] = []
    origin = time.monotonic()
    for beat in beats:
        print(f"  beat {beat.id} ({beat.seconds + beat.pause_after:.1f}s)", flush=True)
        t0 = time.monotonic()
        try:
            run_beat(page, beat, password)
        except Exception as exc:
            print(f"    ! {beat.id} failed: {str(exc)[:120]}", flush=True)
        pace(beat, t0)
        spans.append({
            "id": beat.id,
            "start": round(t0 - origin, 3),
            "end": round(time.monotonic() - origin, 3),
            "narration": round(beat.seconds + beat.pause_after, 3),
        })
    return spans


def run_beat(page, beat: Beat, password: str) -> None:

    if beat.id == "01-signin":
        page.goto(APP_URL, wait_until="networkidle")
        page.wait_for_timeout(4000)
        scroll_through(page, steps=2, dwell=1200)
        page.mouse.wheel(0, -900)
        page.wait_for_timeout(800)
        sign_in(page, "dev", password)

    elif beat.id == "02-first-answer":
        ask(page, "How concentrated is my portfolio?")
        scroll_through(page, steps=3)

    elif beat.id == "03-same-question":
        page.get_by_role("button", name="Sign out").click()
        page.wait_for_timeout(2500)
        sign_in(page, "walter", password)
        ask(page, "Should I buy more NVDA?")
        scroll_through(page, steps=3)

    elif beat.id == "04-fanout":
        ask(page, "How are capital gains taxed and how is SPY doing?")
        scroll_through(page, steps=4)

    elif beat.id == "05-portfolio":
        nav(page, "Portfolio")
        scroll_through(page, steps=5, dwell=1100)

    elif beat.id == "06-market":
        nav(page, "Market")
        scroll_through(page, steps=5, dwell=1100)

    elif beat.id == "07-goals":
        nav(page, "Goals")
        scroll_through(page, steps=4, dwell=1100)

    elif beat.id == "08-internals":
        # Under About Fintor now, not a workspace tab - it reports routing
        # tiers, retrieval ranks and a token ledger, which is the engineering
        # story rather than the state of anyone's money. nav() looks for a
        # top-level link and would not find it.
        open_about(page, "AI Internals")
        scroll_through(page, steps=7, dwell=800)

    elif beat.id == "09-close":
        open_about(page, "Architecture")
        scroll_through(page, steps=2, dwell=1200)



# --- main ---------------------------------------------------------------


def launch_browser(pw):
    """Prefer the installed Google Chrome over a downloaded Chromium.

    This machine is macOS 12, and current Playwright refuses to download
    Chromium for it - `playwright install chromium` fails with "does not
    support chromium on mac12". Driving the system Chrome sidesteps the
    download entirely and costs nothing in fidelity: video recording is a
    browser-context feature, not a build-specific one.

    Falls back to the bundled Chromium where one exists, so this still works on
    a machine that is not stuck on Monterey.
    """
    try:
        return pw.chromium.launch(channel="chrome",
                                  args=["--force-device-scale-factor=1"])
    except Exception as exc:
        print(f"  system Chrome unavailable ({str(exc)[:60]}); trying bundled Chromium")
        return pw.chromium.launch(args=["--force-device-scale-factor=1"])


def _published_password() -> str:
    """The demo credential from config.yaml."""
    import yaml

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    return str(cfg.get("auth", {}).get("demo_password", ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    # Defaults to the credential config.yaml publishes, so a recording needs
    # no environment setup. Still overridable for an instance started with
    # FINTOR_DEMO_PASSWORD.
    ap.add_argument("--password", default=_published_password(),
                    help="sign-in password; defaults to the one in config.yaml")
    ap.add_argument("--skip-audio", action="store_true",
                    help="reuse existing clips in build/demo/audio")
    args = ap.parse_args()

    beats, voice, rate = load_beats()

    print(f"narration: {voice} @ {rate} wpm")
    if args.skip_audio:
        for i, beat in enumerate(beats, 1):
            beat.seconds = probe_seconds(AUDIO / f"{i:02d}-{beat.id}.aiff")
    else:
        render_audio(beats, voice, rate)

    total = sum(b.seconds + b.pause_after for b in beats)
    print(f"\ntotal narration: {total/60:.2f} min ({total:.0f}s)")
    if not 5 * 60 <= total <= 10 * 60:
        print(f"!! outside the brief's 5-10 minute window - edit narration.toml")

    if VIDEO.exists():
        shutil.rmtree(VIDEO)
    VIDEO.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    print("\nrecording...")
    with sync_playwright() as pw:
        browser = launch_browser(pw)
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(VIDEO),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()
        spans = []
        try:
            spans = walk(page, beats, args.password)
        finally:
            # The video is only flushed to disk on close.
            context.close()
            browser.close()

    produced = sorted(VIDEO.glob("*.webm"))
    if not produced:
        print("no video produced", file=sys.stderr)
        return 1
    raw = VIDEO / "raw.webm"
    produced[0].rename(raw)
    (BUILD / "timings.json").write_text(json.dumps(spans, indent=1), encoding="utf-8")
    wall = spans[-1]["end"] if spans else 0
    print(f"wall clock: {wall/60:.2f} min   narration: "
          f"{sum(s['narration'] for s in spans)/60:.2f} min")
    for sp in spans:
        over = (sp["end"] - sp["start"]) - sp["narration"]
        if over > 2:
            print(f"   {sp['id']} ran {over:+.1f}s over - the mux will fit it per beat")
    print(f"\nsilent footage: {raw}  ({raw.stat().st_size/1e6:.1f} MB)")
    print("next: .venv/bin/python scripts/mux_demo.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
