#!/usr/bin/env python3
"""Record one or more storyboard scenes against the running Fintor app.

    .venv/bin/python scripts/record_scene.py s1 s2

Scenes are recorded individually (or in short consecutive runs where one scene
leaves the state the next one needs) rather than as a single nine-minute take.
A bad scene is then re-shot on its own instead of invalidating the whole
recording - which is what happened to every earlier attempt.

HOW THE TIMING WORKS, because this is the part that was broken before:

* A black overlay covers the page while the app loads and settles. Removing it
  is t=0 - a hard visual origin that survives Playwright's variable start-up
  delay. Post-processing finds the first non-black frame and trims there.
* Every action then fires on a MONOTONIC WALL CLOCK offset from t=0, at the
  timestamp the storyboard says, which is the timestamp at which the anchoring
  word is actually spoken.
* Nothing is re-timed afterwards. The previous recorder stretched clips with
  `setpts` to fit, which is what let drift accumulate; here the browser is
  simply driven in real time and the video is used as shot.

The mouse pointer is not captured in a browser video, so a synthetic cursor is
drawn into the page and moved with it. Clicks are real Playwright clicks - the
drawn cursor is cosmetic and is always moved to the element first.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

DEMO = REPO / "build" / "demo"
SCENES_DIR = DEMO / "scenes"
RAW = DEMO / "raw"
APP_URL = "http://localhost:8501"

# The gate pre-fills PERSONAS[1] - "dev" - so arriving at the bare URL and then
# clicking Dev's card changes nothing on screen, and the narration line
# "clicking one fills the form for you" would have no visible referent. Opening
# on ?account=maya is the state the app itself produces when Maya's card is
# clicked, so the Dev click is a real, visible switch. No fabrication: this is
# the app's own URL contract, not a doctored screenshot.
S1_ENTRY = "?account=maya"
VIEWPORT = {"width": 1600, "height": 900}
FPS = 25

CURSOR_JS = """
(() => {
  if (window.__fintorCursor) return;
  const c = document.createElement('div');
  c.id = '__fintor_cursor';
  c.style.cssText = [
    'position:fixed','left:0','top:0','width:22px','height:22px',
    'z-index:2147483646','pointer-events:none','will-change:transform',
    'transform:translate(-100px,-100px)',
    "background:url(\\"data:image/svg+xml;utf8," +
      encodeURIComponent('<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'22\\' height=\\'22\\' viewBox=\\'0 0 22 22\\'>' +
      '<path d=\\'M3 2 L3 17 L7.2 13.2 L9.9 19.4 L12.6 18.2 L10 12.1 L15.6 12.1 Z\\' ' +
      'fill=\\'%23ffffff\\' stroke=\\'%23111111\\' stroke-width=\\'1.4\\' stroke-linejoin=\\'round\\'/></svg>') + "\\")",
    'background-repeat:no-repeat'
  ].join(';');
  document.body.appendChild(c);
  window.__fintorCursor = c;
  window.__fintorMove = (x, y, ms) => {
    c.style.transition = ms > 0 ? `transform ${ms}ms cubic-bezier(.33,.0,.2,1)` : 'none';
    c.style.transform = `translate(${x}px, ${y}px)`;
  };
})();
"""

CLAPPER_JS = """
(() => {
  const d = document.createElement('div');
  d.id = '__fintor_clapper';
  d.style.cssText = 'position:fixed;inset:0;background:#000;z-index:2147483647;pointer-events:none';
  document.documentElement.appendChild(d);
})();
"""

DROP_CLAPPER_JS = """
(() => { const d = document.getElementById('__fintor_clapper'); if (d) d.remove(); })();
"""


class Clock:
    """Wall clock anchored at the moment the clapper is dropped."""

    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.late: list[tuple[float, float]] = []

    def now(self) -> float:
        return time.monotonic() - self.t0

    def until(self, t: float) -> None:
        """Block until scene-time `t`. Records any overrun instead of hiding it."""
        slip = self.now() - t
        if slip > 0.05:
            self.late.append((t, round(slip, 3)))
            return
        while self.now() < t:
            time.sleep(min(0.01, max(0.0, t - self.now())))


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


_LAST_POS: list[float] = [1290.0, 505.0]


def ensure_cursor(page) -> None:
    """Re-draw the cursor after a navigation wiped it.

    Clicking an account card is a real navigation - the cards are
    `<a href="?account=dev">`, which is how the app actually works - so window
    globals and injected nodes do not survive it. The init script re-runs on
    load; this restores the LAST POSITION too, otherwise the pointer would snap
    back off-screen and jump on the next move.
    """
    if page.evaluate("typeof window.__fintorMove === 'function'"):
        return
    page.evaluate(CURSOR_JS)
    page.evaluate(f"window.__fintorMove({_LAST_POS[0]}, {_LAST_POS[1]}, 0)")


def cursor_to(page, selector: str, ms: int = 600, *, dx: float = 0.5,
              dy: float = 0.5) -> tuple[float, float] | None:
    ensure_cursor(page)
    box = page.locator(selector).first.bounding_box()
    if not box:
        print(f"    ! no bounding box for {selector}")
        return None
    x = box["x"] + box["width"] * dx
    y = box["y"] + box["height"] * dy
    page.evaluate(f"window.__fintorMove({x}, {y}, {ms})")
    _LAST_POS[0], _LAST_POS[1] = x, y
    return x, y



# --- page helpers -------------------------------------------------------
#
# Navigation is a CLICK on the top nav, never a URL change. Streamlit treats a
# nav click as a rerun and repaints in ~300ms; a URL navigation is a full app
# reload and blanks the page for ~2s, which would land in the middle of a
# narrated sentence.

DONE = "Answered"
QUESTIONS = {
    # Dev and Walter open with the SAME first prompt - that pairing is in
    # personas.py and is the point of scenes 3 and 4, not a coincidence.
    "nvda": "Should I buy more NVDA?",
    # Routes to exactly two specialists, market + tax, on tier 1 every time -
    # verified with heuristic_route before it was written down here, because
    # "the two agents run concurrently" is narrated over it.
    "dual": "Capital gains tax on selling VTI, and the performance of "
            "the S&P 500 this year?",
}


def nav(page, title: str) -> None:
    """Click a flat top-nav tab.

    Matched on data-testid + contained text, not on the accessible name: each
    link's text begins with its material-icon ligature ("forum\n\nChat"), so a
    get_by_role(name="Chat", exact=True) matches nothing at all.
    """
    page.locator('[data-testid="stTopNavLink"]').filter(
        has_text=title).first.click()
    page.wait_for_timeout(250)


def nav_about(page, title: str) -> None:
    """Open the About Fintor dropdown and pick a page from it."""
    page.get_by_text("About Fintor", exact=True).first.click()
    page.wait_for_timeout(400)
    page.locator('[data-testid="stTopNavDropdownLink"]').filter(
        has_text=title).first.click()
    page.wait_for_timeout(300)


def open_about_menu(page) -> None:
    page.get_by_text("About Fintor", exact=True).first.click()
    page.wait_for_timeout(300)


def close_menu(page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)


def ask(page, question: str) -> int:
    """Submit a question. Returns the chat-message count to wait past.

    Counting MESSAGES, not completion labels. Only the current turn renders a
    status widget - `turns()` replays history as plain markdown - so after the
    second question the "Answered" count is 1 before and 1 after, and a
    label-based wait never fires. It silently burned the whole budget and the
    scene was then driven from a timeout rather than from the real completion:
    measured as "18.8s" for a turn that had actually finished in 12s.
    """
    before = page.locator('[data-testid="stChatMessage"]').count()
    box = page.locator('[data-testid="stChatInputTextArea"]')
    box.fill(question)
    box.press("Enter")
    return before


WORKING = "Working on it…"


def answered(page, before: int) -> bool:
    """The running status label is gone and both messages are on the page.

    The label is the only signal that tracks the turn itself: the message
    count jumps the instant Streamlit paints the assistant container, which
    is before any work has been done, and the completion label is re-used
    across turns. `st.status` starts at "Working on it…" and is updated to
    "Answered" on completion, so the disappearance of the former is the edge.
    """
    return (page.locator('[data-testid="stChatMessage"]').count() >= before + 2
            and page.get_by_text(WORKING, exact=True).count() == 0)


def wait_answered(page, before: int, budget_s: float) -> tuple[float, bool]:
    """Wait for this turn to finish. Returns (seconds, completed).

    Waits for the running label to APPEAR first, so a check that lands in the
    gap between pressing Enter and Streamlit painting the status cannot
    report instant success. Returns the completion flag rather than just the
    elapsed time: a timeout and a fast answer are both "2 seconds" otherwise,
    and that difference is exactly what went unnoticed before.
    """
    t0 = time.monotonic()
    try:
        page.wait_for_selector(f'text="{WORKING}"', timeout=8_000)
    except Exception:
        pass                                   # already finished, or never shown
    while time.monotonic() - t0 < budget_s:
        if answered(page, before):
            return time.monotonic() - t0, True
        page.wait_for_timeout(250)
    return time.monotonic() - t0, False


# Streamlit scrolls an inner <section data-testid="stMain">, NOT the window.
# document.scrollingElement.scrollHeight is 0 and window.scrollTo is a silent
# no-op - every scroll in an earlier version of this file did nothing at all,
# which is why the Portfolio page sat at the top while the narration described
# the correlation matrix. Probed, not guessed: the only element on the page
# with overflowY:auto and scrollHeight > clientHeight is that section.
SCROLLER = 'section[data-testid="stMain"]'


def _scroll_js(body: str) -> str:
    return f"""(arg) => {{
        const sc = document.querySelector('{SCROLLER}')
                   || document.scrollingElement || document.documentElement;
        {body}
    }}"""


def scroll_to(page, selector: str, ms: int = 900, offset: int = -90) -> None:
    """Smooth-scroll an element into view, then VERIFY it got there.

    One scroll is not enough on this app. Plotly figures mount after the first
    paint and change the page height underneath an in-flight smooth scroll, so
    the view lands short and stays there. That is what put the Portfolio page
    at the top while the narration was describing the correlation matrix.

    So: scroll, measure, and re-assert up to three times, the last one
    instantly. Measuring the element's own rect rather than trusting scrollY,
    because the thing that moved is the element, not the viewport.
    """
    loc = page.locator(selector).first
    if loc.count() == 0:
        print(f"    ! scroll target missing: {selector}")
        return
    for attempt in range(3):
        behavior = "smooth" if attempt < 2 else "auto"
        page.evaluate(_scroll_js("""
            const [sel, off, behavior] = arg;
            const el = document.querySelector(sel);
            if (!el) return;
            const y = el.getBoundingClientRect().top
                      - sc.getBoundingClientRect().top + sc.scrollTop + off;
            sc.scrollTo({top: Math.max(0, y), behavior});
        """), [selector, offset, behavior])
        page.wait_for_timeout(min(ms, 1200) if attempt == 0 else 450)
        top = page.evaluate(_scroll_js("""
            const el = document.querySelector(arg);
            return el ? el.getBoundingClientRect().top
                        - sc.getBoundingClientRect().top : null;
        """), selector)
        if top is None:
            return
        if abs(top - (-offset)) <= 60:          # within 60px of where it was asked for
            return
    print(f"    ! scroll did not settle on {selector} (top={top:.0f}, "
          f"wanted ~{-offset})")


def scroll_by(page, dy: int) -> None:
    page.evaluate(_scroll_js("sc.scrollBy({top: arg, behavior: 'smooth'});"), dy)


def scroll_top(page) -> None:
    page.evaluate(_scroll_js("sc.scrollTo({top: 0, behavior: 'auto'});"))


def has_text(page, text: str) -> str:
    """A selector for the card containing `text`, for scroll targets."""
    return f'div[class*="st-key-card-{text}"]'


def sign_in_as(page, who: str, password: str) -> None:
    page.goto(f"{APP_URL}?account={who}", wait_until="networkidle")
    page.wait_for_selector('[data-testid="stTextInput"] input', timeout=30_000)
    boxes = page.locator('[data-testid="stTextInput"] input')
    if not boxes.nth(1).input_value():
        boxes.nth(1).fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_selector('[data-testid="stTopNavLink"]', timeout=60_000)


def demo_password() -> str:
    import yaml
    raw = yaml.safe_load((REPO / "config.yaml").read_text())
    return (raw.get("auth", {}) or {}).get("demo_password", "fintor")


# --- scene bodies -------------------------------------------------------
#
# One function per scene. Each takes (page, clock, cues) where `cues` maps a
# cue index to its absolute time, and drives the browser against the clock.


def scene_s1(page, clock, at) -> None:
    """Persona gallery. All six cards stay in frame for the whole scene."""
    cards = {p: f'a.signin-account-link[href="?account={p}"]'
             for p in ("maya", "dev", "walter", "priya", "aisha", "sam")}

    clock.until(at(0))                      # hold, no motion

    clock.until(at(1))                      # "There are six sample accounts"
    scroll_top(page)

    for idx, who in ((2, "maya"), (3, "dev"), (4, "walter"),
                     (5, "priya"), (6, "aisha"), (7, "sam")):
        clock.until(at(idx) - 0.35)         # cursor arrives ON the name
        cursor_to(page, cards[who], ms=520, dy=0.30)

    clock.until(at(8) - 0.35)               # "clicking one fills the form"
    cursor_to(page, cards["dev"], ms=400, dy=0.30)
    clock.until(at(8))
    page.locator(cards["dev"]).first.click()
    page.wait_for_selector("a.signin-account-link", timeout=30_000)
    ensure_cursor(page)

    clock.until(at(9))                      # "Two of them open with the same question"
    cursor_to(page, f'{cards["dev"]} .signin-account-journey', ms=500)
    clock.until(at(9) + 2.6)
    cursor_to(page, f'{cards["walter"]} .signin-account-journey', ms=900)


def scene_s2(page, clock, at) -> None:
    """Sign in, on the words 'We will sign in as Dev'."""
    clock.until(at(0))
    ensure_cursor(page)
    cursor_to(page, 'button:has-text("Sign in")', ms=700)

    clock.until(at(1) - 0.9)                # cursor settles before the click
    cursor_to(page, 'button:has-text("Sign in")', ms=450)
    clock.until(at(1))                      # "We will sign in as Dev"
    page.get_by_role("button", name="Sign in").click()

    page.wait_for_selector('[data-testid="stTopNavLink"]', timeout=60_000)
    ensure_cursor(page)
    landed = clock.now()
    print(f"    chat painted at t={landed:.2f}s "
          f"(must be <= {at(2):.2f}s)")
    if landed > at(2):
        print(f"    ! LATE by {landed - at(2):.2f}s")
    page.evaluate("window.__fintorMove(1180, 470, 500)")




def scene_s3(page, clock, at) -> None:
    """Dev's first question, answered live so the steps are real.

    The app answers far faster than the narration describing it - measured at
    ~2s against a 34s window. So the status panel is RE-OPENED once the turn
    completes and left open through blocks 7-9, which narrate the guard, the
    three router tiers and the agents running. What is on screen then is the
    real step list with the real per-node timings, not a frozen spinner and
    not a slowed-down replay.
    """
    clock.until(at(0))
    before = ask(page, QUESTIONS["nvda"])

    budget = at(2) - at(0) - 1.0
    took, ok = wait_answered(page, before, budget)
    print(f"    dev answer in {took:.1f}s (budget {budget:.1f}s)"
          f"{'' if ok else '  ** TIMED OUT **'}")

    # Re-open the collapsed status so the completed steps stay visible.
    page.wait_for_timeout(600)
    panel = page.get_by_text(DONE, exact=True).first
    cursor_to(page, f'text="{DONE}"', ms=400)
    panel.click()
    page.wait_for_timeout(500)
    # The panel sits near the fold; bring the whole step list into frame.
    scroll_by(page, 430)
    page.wait_for_timeout(600)
    print(f"    step list re-opened at t={clock.now():.2f}s")

    clock.until(at(1))                        # blocks 8-9 over the real steps
    clock.until(at(2) - 1.4)
    panel.click()                             # collapse, back to the answer
    page.wait_for_timeout(400)

    clock.until(at(2))
    scroll_by(page, 320)                      # citations under the answer
    clock.until(at(3))                        # "Underneath ... live or cached"
    scroll_by(page, 260)
    clock.until(at(4) - 0.4)                  # "It is all on the AI Internals page"
    scroll_top(page)
    page.wait_for_timeout(500)
    cursor_to(page, 'text="About Fintor"', ms=450)
    clock.until(at(4))
    open_about_menu(page)
    clock.until(at(4) + 4.0)
    close_menu(page)


def scene_s4(page, clock, at) -> None:
    """Sign out, back in as Walter, ask Dev's question verbatim."""
    clock.until(at(0))
    cursor_to(page, 'button:has-text("Sign out")', ms=500)
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_selector("a.signin-account-link", timeout=60_000)
    ensure_cursor(page)
    page.wait_for_timeout(600)

    cursor_to(page, 'a.signin-account-link[href="?account=walter"]', ms=550, dy=0.3)
    page.locator('a.signin-account-link[href="?account=walter"]').first.click()
    page.wait_for_selector("a.signin-account-link", timeout=30_000)
    ensure_cursor(page)
    cursor_to(page, 'button:has-text("Sign in")', ms=450)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_selector('[data-testid="stTopNavLink"]', timeout=60_000)
    ensure_cursor(page)
    print(f"    walter signed in at t={clock.now():.2f}s (ask cue {at(1):.2f}s)")

    clock.until(at(1))                        # "We ask Walter the identical question"
    before = ask(page, QUESTIONS["nvda"])
    budget = at(2) - at(1) - 1.0
    took, ok = wait_answered(page, before, budget)
    print(f"    walter answer in {took:.1f}s (budget {budget:.1f}s)"
          f"{'' if ok else '  ** TIMED OUT **'}")
    clock.until(at(2))
    scroll_by(page, 300)


def scene_s5(page, clock, at) -> None:
    """One question, two specialists, then the roster."""
    clock.until(at(0) - 1.2)
    scroll_top(page)
    clock.until(at(0))
    before = ask(page, QUESTIONS["dual"])

    budget = at(2) - at(0) - 1.0
    took, ok = wait_answered(page, before, budget)
    print(f"    fan-out answer in {took:.1f}s (budget {budget:.1f}s)"
          f"{'' if ok else '  ** TIMED OUT **'}")

    # Same treatment as s3, and for the same reason: the turn completes in
    # under 3s while block 19 spends eleven seconds on "the two agents run
    # concurrently". The re-opened step list names both specialists and times
    # each node, so what is on screen during that sentence is the evidence for
    # it. (An earlier run appeared to take 18.8s; that was a broken wait
    # timing out, not the app being slow.)
    page.wait_for_timeout(500)
    panel = page.get_by_text(DONE, exact=True).first
    cursor_to(page, f'text="{DONE}"', ms=400)
    panel.click()
    page.wait_for_timeout(500)
    scroll_by(page, 420)

    clock.until(at(1))                        # "the two agents run concurrently"
    clock.until(at(2) - 1.4)
    panel.click()                             # collapse, back to the merged answer
    page.wait_for_timeout(400)

    clock.until(at(2))
    scroll_by(page, 340)                      # merged answer + renumbered citations

    clock.until(at(3) - 3.0)                  # "There are six specialists in total"
    nav_about(page, "AI Internals")
    page.wait_for_selector('[class*="st-key-card-in-roster"]', timeout=20_000)
    page.wait_for_timeout(700)                # let the rerun settle, else the
    clock.until(at(3))                        # scroll is undone by the repaint
    scroll_to(page, '[class*="st-key-card-in-roster"]', ms=1200, offset=-110)


def scene_s6(page, clock, at) -> None:
    """Portfolio: computed in Python, then the correlation matrix."""
    clock.until(at(0) - 1.6)                  # painted by the time it is named
    nav(page, "Portfolio")
    scroll_top(page)

    clock.until(at(1))                        # total, allocation, holdings
    clock.until(at(2))                        # right rail
    cursor_to(page, '[class*="st-key-card-pf-risk"]', ms=700)

    clock.until(at(3))                        # "This is a correlation matrix"
    scroll_to(page, '[class*="st-key-card-pf-correlation"]', ms=1200, offset=-80)

    clock.until(at(4))                        # hold on the matrix
    clock.until(at(5) - 1.6)                  # "Market data is live, and keyless"
    nav(page, "Market")
    scroll_top(page)


def scene_s7(page, clock, at) -> None:
    """Market: real freshness state, price history, indexed benchmark."""
    clock.until(at(0))
    scroll_top(page)
    clock.until(at(1))                        # "Price history ... 20 and 50 day"
    scroll_to(page, '[class*="st-key-card-mk-price"]', ms=1200, offset=-90)
    clock.until(at(2))                        # drawdown / volatility
    scroll_to(page, '[class*="st-key-card-mk-quotes"]', ms=1000, offset=-90)
    clock.until(at(3))                        # indexed-to-100 benchmark
    scroll_to(page, '[class*="st-key-card-mk-compare"]', ms=1200, offset=-90)


def scene_s8(page, clock, at) -> None:
    """Goals: projection, the spread, the assumptions."""
    clock.until(at(0) - 1.6)
    nav(page, "Goals")
    scroll_top(page)

    clock.until(at(1))                        # dashed target line
    scroll_to(page, '[class*="st-key-card-gl-projection"]', ms=1100, offset=-90)
    clock.until(at(2))                        # +/- 2pp table
    scroll_to(page, '[class*="st-key-card-gl-scenarios"]', ms=1200, offset=-90)
    clock.until(at(3))                        # assumptions
    scroll_to(page, '[class*="st-key-card-gl-assumptions"]', ms=1100, offset=-90)


def scene_s9(page, clock, at) -> None:
    """AI Internals, top to bottom, in the order the narration takes it."""
    clock.until(at(0) - 2.2)                  # on screen as block 41 opens
    nav_about(page, "AI Internals")
    scroll_top(page)

    clock.until(at(0))                        # routing decision
    scroll_to(page, '[class*="st-key-card-in-routing"]', offset=-90)

    clock.until(at(1))                        # persona conditioning, graph trace
    scroll_to(page, '[class*="st-key-card-in-persona"]', offset=-90)
    clock.until(at(1) + 5.0)
    scroll_to(page, '[class*="st-key-card-in-trace"]', offset=-90)

    clock.until(at(2))                        # retrieval candidates
    scroll_to(page, '[class*="st-key-card-in-retrieval"]', ms=1200, offset=-90)

    clock.until(at(3))                        # model calls, cache tiers, cost
    scroll_to(page, '[class*="st-key-card-in-calls"]', ms=1200, offset=-90)
    # KNOWN LIMIT, stated rather than worked around: the `exact` rows are the
    # last ones (the repeat is asked second) and st.dataframe scrolls
    # internally, so they sit below the grid's own fold. A mouse wheel over
    # the grid scrolls the PAGE, not the grid, and carried the shot past the
    # card entirely - tried and reverted. What IS on screen is the tier,
    # token and cost columns, and the legend under the table naming the exact
    # layer and its zero-token cost. Block 46's first sentence is fully
    # supported; its second is supported by the legend, not by a visible row.

    clock.until(at(4))                        # hold on the cache rows
    clock.until(at(5))                        # Langfuse link, then workflow graph
    scroll_to(page, '[class*="st-key-card-in-trace-link"]', offset=-90)
    clock.until(at(5) + 4.5)
    scroll_to(page, '[class*="st-key-card-in-graph"]', ms=1200, offset=-90)


def scene_s10(page, clock, at) -> None:
    """Architecture, specs, governance. The MCP inset is composited later."""
    clock.until(at(0) - 2.0)
    nav_about(page, "Architecture")
    scroll_top(page)

    clock.until(at(0))                        # "Behind it sit the specifications"
    scroll_by(page, 400)
    clock.until(at(0) + 4.5)
    nav_about(page, "Design Document")
    scroll_top(page)

    clock.until(at(1) - 1.5)                  # MCP - inset composited over this
    nav_about(page, "Governance")
    scroll_top(page)

    clock.until(at(2))                        # traceability, coverage, offline tests
    scroll_by(page, 520)
    clock.until(at(2) + 5.0)
    scroll_by(page, 460)


# --- pre-roll setup -----------------------------------------------------
#
# Each chunk is recorded on its own, so the app must be put into the state the
# chunk starts from BEFORE the clapper drops. None of this is in the video.


def setup_s3(page) -> None:
    sign_in_as(page, "dev", demo_password())


def setup_s6(page) -> None:
    sign_in_as(page, "walter", demo_password())


def setup_s9(page) -> None:
    """Walter signed in, with a question history and a REAL cache hit on record.

    Block 46 says a repeated question is served from disk at zero tokens and
    zero cost, and the model-calls table is on screen while it is said. So the
    question is genuinely asked twice here - the second one hits the exact-match
    layer and lands in the table as its own row at $0.00. Nothing is staged:
    if the second call had missed, the table would show a miss and the claim
    would be reported as undemonstrated.
    """
    sign_in_as(page, "walter", demo_password())
    for n in (1, 2):
        before = ask(page, QUESTIONS["dual"])
        took, ok = wait_answered(page, before, 180)
        print(f"    setup: dual-intent ask #{n} {'done' if ok else 'TIMED OUT'} "
              f"in {took:.1f}s")
        page.wait_for_timeout(1500)


SETUPS = {"s3": setup_s3, "s6": setup_s6, "s9": setup_s9}


BODIES = {"s1": scene_s1, "s2": scene_s2, "s3": scene_s3,
          "s4": scene_s4, "s5": scene_s5, "s6": scene_s6,
          "s7": scene_s7, "s8": scene_s8, "s9": scene_s9,
          "s10": scene_s10}


def postprocess(webm: Path, out: Path, duration: float) -> dict:
    """Trim to the clapper drop and encode to a fixed-duration mp4."""
    ff = ffmpeg()
    probe = subprocess.run(
        [ff, "-i", str(webm), "-vf",
         "blackdetect=d=0.05:pix_th=0.06", "-an", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    # The clapper is the only deliberate black in the capture, and it is the
    # FIRST one - Playwright starts recording at context creation, so the page
    # load precedes it. Its black_end is t=0. No fallback to zero: a missed
    # clapper would silently offset the whole scene, which is exactly the class
    # of bug this rebuild is fixing.
    start = None
    for line in probe.splitlines():
        if "black_end:" not in line:
            continue
        for tok in line.split():
            if tok.startswith("black_end:"):
                start = float(tok.split(":")[1])
        break
    if start is None:
        raise SystemExit("no clapper found in the capture - refusing to guess t=0")
    subprocess.run(
        [ff, "-y", "-ss", f"{start:.3f}", "-i", str(webm),
         "-t", f"{duration:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "slow", "-crf", "20",
         "-pix_fmt", "yuv420p", "-an", str(out)],
        check=True, capture_output=True)
    return {"clapper_end": round(start, 3), "duration": duration}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scenes", nargs="+", help="scene ids, e.g. s1 s2")
    ap.add_argument("--url", default=APP_URL)
    args = ap.parse_args()

    man = json.loads((DEMO / "production_manifest.json").read_text())
    by_id = {s["id"]: s for s in man["scenes"]}
    for sid in args.scenes:
        if sid not in by_id:
            raise SystemExit(f"unknown scene {sid}")
        if sid not in BODIES:
            raise SystemExit(f"no recorded body for {sid} yet")

    first, last = by_id[args.scenes[0]], by_id[args.scenes[-1]]
    t_in, t_out = first["in"], last["out"]
    print(f"recording {' '.join(args.scenes)}: {t_in:.2f}s -> {t_out:.2f}s "
          f"({t_out - t_in:.2f}s)")

    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    for stale in RAW.glob("*.webm"):
        stale.unlink()

    from playwright.sync_api import sync_playwright
    from scripts.record_demo import launch_browser

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        ctx = browser.new_context(viewport=VIEWPORT,
                                  record_video_dir=str(RAW),
                                  record_video_size=VIEWPORT,
                                  device_scale_factor=1)
        page = ctx.new_page()
        page.add_init_script(CURSOR_JS)   # before goto: survives every navigation
        first_id = args.scenes[0]
        entry = args.url + (S1_ENTRY if first_id == "s1" else "")
        page.goto(entry, wait_until="networkidle")
        page.wait_for_selector("a.signin-account-link", timeout=60_000)
        page.wait_for_timeout(1200)       # let ?account= apply and the rerun land
        if first_id in SETUPS:
            print(f"  pre-roll setup for {first_id} (not recorded)")
            SETUPS[first_id](page)
            page.wait_for_timeout(800)
        page.evaluate(CLAPPER_JS)
        page.evaluate(CURSOR_JS)
        page.evaluate("window.__fintorMove(1290, 505, 0)")   # neutral park
        page.wait_for_timeout(2500)          # let fonts and layout settle

        page.evaluate(DROP_CLAPPER_JS)
        clock = Clock()

        for sid in args.scenes:
            sc = by_id[sid]
            cues = [c["at"] - t_in for c in sc["cues"]]
            print(f"  {sid}: {sc['title']}")
            BODIES[sid](page, clock, lambda i: cues[i])

        clock.until(t_out - t_in)
        page.wait_for_timeout(250)
        video = page.video
        ctx.close()
        browser.close()
        raw = Path(video.path())

    out = SCENES_DIR / f"{'_'.join(args.scenes)}.mp4"
    info = postprocess(raw, out, t_out - t_in)
    print(f"  clapper dropped at {info['clapper_end']:.3f}s in the raw capture")
    if clock.late:
        print(f"  ! {len(clock.late)} cue(s) fired late: {clock.late}")
    else:
        print("  all cues fired on time")
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
