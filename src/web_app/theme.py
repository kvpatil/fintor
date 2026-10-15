"""Theme CSS.

Tabular numerals are the point of this file. Financial figures that shift
horizontally as values update read as sloppy, and proportional digits are the
single most common tell that a dashboard was not built by someone who looks at
numbers for a living. One CSS line fixes it everywhere.
"""

from __future__ import annotations

import streamlit as st

CSS = """
<style>
:root {
  --fin-ink: #17211d;
  /* Darkened from #5f6b66: 5.3:1 -> 6.3:1 on the light ground. Size was the real
     legibility problem, but at 14px the extra presence costs nothing. */
  --fin-muted: #55605b;
  --fin-line: #e2ded4;
  --fin-accent: #1f6f5c;
  --fin-warn: #9a6a1b;
  /* Card/chip ground. A token because it was hardcoded #fffefb in five rules,
     every one of which would have stayed light-on-dark. */
  --fin-paper: #fffefb;

  /* Type scale. These exist because the small sizes drifted down to 11.5px by
     being hand-picked one rule at a time. Nothing goes below --fs-xs, and
     tests/test_theme.py fails the build if a raw literal sneaks under it. */
  --fs-xs: 0.875rem;    /* 14px - chips, uppercase eyebrows */
  --fs-sm: 0.9375rem;   /* 15px - secondary text, breadcrumb, identity */
  --fs-md: 1rem;        /* 16px - body */

  /* Navigation colour, in two layers. Layer one: a tint saying what KIND of page
     a tab is - workspace you operate, reference you consult. Layer two: a dot
     saying what the system is doing, painted from DataStatus and the budget.
     The dot variables are overwritten per rerun by chrome.nav_state_style(). */
  --tab-workspace: rgba(31, 111, 92, 0.08);
  --tab-reference: rgba(90, 104, 120, 0.10);
  --dot-live: #1f6f5c;
  --dot-cached: #8a948f;
  --dot-attention: #c07c12;
  --dot-market: transparent;
  --dot-portfolio: transparent;
  --dot-internals: transparent;

  /* Content measure. Without this the app is full-bleed: at 1500px the prompt
     buttons stretch ~1370px and running prose hits an unreadable measure. The
     .gate-wrap max-width that was supposed to do this never applied, because
     Streamlit renders its columns outside any wrapper div we emit. */
  --fin-measure: 1120px;
  --fin-prose: 72ch;

  /* Distance from the top of the viewport to the first thing on the page.
     Streamlit's top nav is a FIXED 60px header that overlays the content - the
     main container starts at y=0 behind it - so this has to clear 60px before it
     buys any visible air. Measured in the browser: 3.5rem leaves the header row
     12px clear of the nav. Below 3rem the Switch button is clipped. */
  --fin-top-gap: 3.5rem;
}

/* Streamlit sizes this padding for an app with NO top nav, so with
   position="top" it stacks below the bar instead of being absorbed by it -
   which is the dead band between the tabs and the content. */
[data-testid="stMainBlockContainer"] {
  padding-top: var(--fin-top-gap);
  max-width: var(--fin-measure);
  margin-left: auto;
  margin-right: auto;
}

html, body, [class*="st-"] { font-feature-settings: "kern" 1; }

/* Every figure aligns in its column and stops jittering as values update. */
[data-testid="stMetricValue"], [data-testid="stMetricDelta"],
.stDataFrame, code, pre, .fin-num, table td, table th {
  font-variant-numeric: tabular-nums lining-nums;
  font-feature-settings: "tnum" 1, "lnum" 1;
}

/* "Fintor Serif" IS Source Serif 4. It is aliased because Streamlit bundles a
   family called "Source Serif" and silently DROPS a declared fontFace whose
   name collides with it - the face never reached document.fonts at all. */
h1, h2, h3, h4 { font-family: "Fintor Serif", Georgia, serif;
                 letter-spacing: -0.012em; font-weight: 650; }
h1 { font-size: 1.72rem; }

/* Hairline rules instead of drop shadows - restraint reads as considered. */
[data-testid="stMetric"] {
  border: 1px solid var(--fin-line);
  border-radius: 10px;
  padding: 12px 14px 8px;
  background: var(--fin-paper);
}
[data-testid="stSidebar"] { border-right: 1px solid var(--fin-line); }

.fin-chip {
  display: inline-block; padding: 2px 9px; margin: 0 4px 4px 0;
  border: 1px solid var(--fin-line); border-radius: 999px;
  font-size: var(--fs-xs); color: var(--fin-muted); background: var(--fin-paper);
  font-variant-numeric: tabular-nums;
}
.fin-chip-accent { border-color: var(--fin-accent); color: var(--fin-accent); }
.fin-chip-warn { border-color: var(--fin-warn); color: var(--fin-warn); }

.fin-persona {
  border: 1px solid var(--fin-line); border-left: 3px solid var(--fin-accent);
  border-radius: 8px; padding: 10px 12px; background: var(--fin-paper); margin-bottom: 10px;
}
.fin-persona b { font-size: 0.96rem; }
.fin-persona span { color: var(--fin-muted); font-size: var(--fs-sm); }

/* ---- entry gate ---- */
/* .gate-wrap is a no-op for layout - Streamlit's columns render outside it.
   The real constraint is --fin-measure on stMainBlockContainer above. */
.gate-wrap { margin: 0 auto; }
.gate-logo { margin: 18px 0 2px; }
.gate-logo svg { height: 38px; width: auto; }
.gate-tagline {
  font-family: "Fintor Serif", Georgia, serif;
  font-size: 1.55rem; font-weight: 700; letter-spacing: -0.015em;
  margin: 2px 0 6px;
}
.gate-subline { color: var(--fin-muted); max-width: 60ch; margin: 0 0 26px; }
.gate-ask {
  font-size: var(--fs-xs); letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--fin-accent); margin: 10px 0 10px;
}
.gate-card {
  border: 1px solid var(--fin-line); border-radius: 8px;
  background: var(--fin-paper); padding: 14px 15px 12px; margin-bottom: 8px;
  min-height: 172px;
  display: flex; flex-direction: column;
}
/* Push the figures to the bottom so every card's rule line agrees, however
   many lines the headline takes. */
.gate-card .gate-nums { margin-top: auto; }
.gate-name { font-family: "Fintor Serif", Georgia, serif; font-size: 1.1rem; font-weight: 700; margin: 0; }
.gate-head { margin: 2px 0 8px; font-size: var(--fs-md); }
.gate-meta { color: var(--fin-muted); font-size: var(--fs-sm); margin: 0 0 10px; }
.gate-nums {
  display: flex; gap: 14px; margin: 0; font-size: var(--fs-sm); color: var(--fin-muted);
  font-variant-numeric: tabular-nums lining-nums;
  border-top: 1px solid var(--fin-line); padding-top: 8px;
}
.gate-nums b { color: var(--fin-ink); font-weight: 650; }
.gate-foot { color: var(--fin-muted); font-size: var(--fs-sm); margin: 22px 0 0; max-width: 72ch; }


/* Reference pages are read, not scanned, so they take a narrower measure.
   Headings and figures stay full width; only running text is constrained. */
.fin-prose p, .fin-prose li { max-width: var(--fin-prose); }

/* ---- top navigation ----------------------------------------------------
   Targeted via aria-current and href, never Streamlit's generated emotion class
   hashes, which change between builds. The icons are Material font ligatures, so
   font-size is what sizes them. */

[data-testid="stTopNavLink"] {
  font-size: var(--fs-md) !important;
  font-weight: 500;
  min-height: 38px;
  padding: 6px 14px !important;
  border-radius: 8px;
  gap: 8px;
  background: var(--tab-workspace);
  position: relative;
}
[data-testid="stTopNavLink"] [data-testid="stIconMaterial"] {
  font-size: 20px !important;
  width: 20px; height: 20px;
}
[data-testid="stTopNavLink"]:hover { background: rgba(31, 111, 92, 0.16); }

/* The page you are on: solid, not a wash. */
[data-testid="stTopNavLink"][aria-current="page"] {
  background: var(--fin-accent) !important;
  color: var(--fin-paper) !important;
  font-weight: 600;
}
[data-testid="stTopNavLink"][aria-current="page"] [data-testid="stIconMaterial"] {
  color: var(--fin-paper) !important;
}

/* Reference material reads as a different family from your workspace. */
[data-testid="stTopNavSection"] {
  background: var(--tab-reference);
  border-radius: 8px;
  font-size: var(--fs-md) !important;
  font-weight: 500;
  min-height: 38px;
  padding: 6px 12px !important;
}
[data-testid="stTopNavSection"] [data-testid="stIconMaterial"] { font-size: 20px !important; }

/* State dots. Colour comes from chrome.nav_state_style(), computed server-side
   from DataStatus and the cost meter - transparent until a real observation,
   so the nav can never claim "live" on a cold load. */
[data-testid="stTopNavLink"][href$="/market"]::after,
[data-testid="stTopNavLink"][href$="/portfolio"]::after,
[data-testid="stTopNavLink"][href$="/internals"]::after {
  content: "";
  width: 7px; height: 7px; border-radius: 50%;
  display: inline-block; margin-left: 2px;
}
[data-testid="stTopNavLink"][href$="/market"]::after { background: var(--dot-market); }
[data-testid="stTopNavLink"][href$="/portfolio"]::after { background: var(--dot-portfolio); }
[data-testid="stTopNavLink"][href$="/internals"]::after { background: var(--dot-internals); }

/* ---- top chrome ---- */
.bc { margin: 0; }
.bc ol { list-style: none; display: flex; flex-wrap: wrap; gap: 6px;
         margin: 0; padding: 0; font-size: var(--fs-sm); color: var(--fin-muted); }
.bc li { display: flex; gap: 6px; align-items: baseline; }
.bc-sep { color: var(--fin-line); }
.bc-now { color: var(--fin-ink); font-weight: 600; }

.ident { display: flex; align-items: baseline; justify-content: flex-end;
         gap: 8px; flex-wrap: wrap; }
.ident-who { font-size: var(--fs-sm); font-weight: 600; }
.ident-sub { color: var(--fin-muted); font-weight: 400; }

.chip, .chip-accent, .chip-warn {
  display: inline-block; padding: 1px 8px; border-radius: 999px;
  border: 1px solid var(--fin-line); background: var(--fin-paper);
  font-size: var(--fs-xs); color: var(--fin-muted);
  font-variant-numeric: tabular-nums;
}
.chip-accent { border-color: var(--fin-accent); color: var(--fin-accent); }
.chip-warn { border-color: var(--fin-warn); color: var(--fin-warn); }

.chrome-rule { border-top: 1px solid var(--fin-line); margin: 8px 0 14px; }

/* Streamlit's own secondary text sits right next to ours, so it takes the same
   floor: the persona summary line on the data pages, and every metric label. */
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {
  font-size: var(--fs-sm) !important;
}

.prompt-hint {
  font-size: var(--fs-xs); letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--fin-muted); margin: 14px 0 6px;
}

.fin-disclaimer {
  color: var(--fin-muted); font-size: var(--fs-sm); border-top: 1px solid var(--fin-line);
  padding-top: 8px; margin-top: 14px;
}
.fin-cite { font-size: var(--fs-sm); color: var(--fin-muted); }

/* THEME_RULES is appended here at import time: the light and dark token blocks
   under :root[data-theme="..."], which theme_probe() keeps in sync. Every
   component already styles through the tokens, so swapping them is the whole of
   dark mode. */
</style>
"""


# The dark palette, as a single block. Every colour token in :root is restated
# here; tests/test_theme.py fails if one is missed, because a token that is only
# defined once survives into dark mode unchanged - which is how near-black text
# and a near-white card ground shipped on a dark ground once already.
DARK_TOKENS = """
  --fin-ink: #e7ebe6;
  --fin-muted: #9aa5a0;      /* 7.1:1 on #121714 */
  --fin-line: #333b37;
  --fin-accent: #5bbfa2;
  --fin-warn: #d2a248;
  --fin-paper: #1b211e;
  --tab-workspace: rgba(91, 191, 162, 0.14);
  --tab-reference: rgba(154, 165, 160, 0.12);
  --dot-live: #5bbfa2;
  --dot-cached: #7d8884;
  --dot-attention: #d2a248;
"""

LIGHT_TOKENS = """
  --fin-ink: #17211d;
  --fin-muted: #55605b;
  --fin-line: #e2ded4;
  --fin-accent: #1f6f5c;
  --fin-warn: #9a6a1b;
  --fin-paper: #fffefb;
  --tab-workspace: rgba(31, 111, 92, 0.08);
  --tab-reference: rgba(90, 104, 120, 0.10);
  --dot-live: #1f6f5c;
  --dot-cached: #8a948f;
  --dot-attention: #c07c12;
"""

# Both are explicit and both are attribute-scoped, so whichever one the probe
# selects outranks the plain `:root` block below on specificity - including the
# dark block the server emitted for the first paint.
THEME_RULES = (f':root[data-theme="dark"] {{{DARK_TOKENS}}}\n'
               f':root[data-theme="light"] {{{LIGHT_TOKENS}}}\n')
CSS = CSS.replace("</style>", THEME_RULES + "</style>")

DARK_CSS = f"<style>:root {{{DARK_TOKENS}}}</style>"

# Streamlit's theme menu repaints the page WITHOUT rerunning the script, so
# anything the server decided is stale until the next interaction. Measured:
# switching Dark -> Light left black cards with dark text on a light page, and
# pressing Escape did not fix it. Streamlit also stamps no theme attribute and
# exposes no CSS variables - but the colour it paints on [data-testid="stApp"]
# is always current, so the browser reads that and stamps the attribute itself.
#
# st.components.v1.html rather than st.markdown: markdown strips <script>. The
# iframe is same-origin, so window.parent.document is reachable, and height=0
# keeps it out of the layout.
THEME_PROBE = """
<script>
(function () {
  var doc = window.parent.document;
  var app = doc.querySelector('[data-testid="stApp"]');
  if (!app) { return; }
  function stamp() {
    var m = getComputedStyle(app).backgroundColor.match(/\\d+/g);
    if (!m) { return; }
    var l = 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2];
    var want = l < 128 ? 'dark' : 'light';
    if (doc.documentElement.getAttribute('data-theme') !== want) {
      doc.documentElement.setAttribute('data-theme', want);
    }
  }
  stamp();
  new MutationObserver(stamp).observe(app, {attributes: true});
  // The observer catches the class swap; the interval is the belt-and-braces
  // for a repaint that happens without touching stApp's own attributes.
  setInterval(stamp, 500);
})();
</script>
"""


def theme_probe() -> None:
    """Keep :root[data-theme] in step with whatever Streamlit has painted."""
    import streamlit.components.v1 as components

    components.html(THEME_PROBE, height=0)


def inject() -> None:
    """Base tokens, then the dark swap when the viewer is in dark mode.

    The theme is decided in PYTHON, not in CSS, and that is not a stylistic
    preference - it is the only signal that is correct. Measured in the browser:

      * `@media (prefers-color-scheme: dark)` follows the OPERATING SYSTEM. A
        viewer on a light OS who picks "Dark" in Streamlit's own menu gets a dark
        page with the light tokens still in force - a near-white card ground
        under Streamlit's light-on-dark text, which is invisible. It is wrong in
        the other direction too: a dark OS plus "Light" darkens the tokens under
        a light page.
      * `:root[data-theme="dark"]` never matches. Streamlit stamps nothing on
        `<html>` or `<body>` and exposes no CSS custom properties - that selector
        is an Artifacts convention that was carried here on the assumption it
        applied, and it never did.

    `st.context.theme.type` is the one thing that actually knows, so the server
    emits the block rather than asking the browser to work it out.
    """
    st.markdown(CSS, unsafe_allow_html=True)
    if is_dark():
        # First-paint accuracy only. The probe's attribute-scoped rules outrank
        # this the moment they land, so a stale value here cannot persist.
        st.markdown(DARK_CSS, unsafe_allow_html=True)
    theme_probe()


def chip(label: str, kind: str = "") -> str:
    cls = {"accent": "fin-chip fin-chip-accent", "warn": "fin-chip fin-chip-warn"}.get(kind, "fin-chip")
    return f'<span class="{cls}">{label}</span>'


def is_dark() -> bool:
    """Whether the viewer is currently in dark mode.

    `config.toml` deliberately omits `base`, so the palette follows the viewer's
    preference rather than being pinned. CSS handles that through media queries,
    but Plotly figures are built in Python and have to be *told* - without this
    the charts keep their light hues on a dark page.

    Defaults to light on anything unexpected: `st.context` is unavailable outside
    a script run (tests, the fonts generator), and a wrong guess here is a
    cosmetic miss, never an error worth raising.
    """
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001 - no script context, or an older Streamlit
        return False
