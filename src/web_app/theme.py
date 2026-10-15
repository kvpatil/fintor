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
}

html, body, [class*="st-"] { font-feature-settings: "kern" 1; }

/* Every figure aligns in its column and stops jittering as values update. */
[data-testid="stMetricValue"], [data-testid="stMetricDelta"],
.stDataFrame, code, pre, .fin-num, table td, table th {
  font-variant-numeric: tabular-nums lining-nums;
  font-feature-settings: "tnum" 1, "lnum" 1;
}

h1, h2, h3 { letter-spacing: -0.01em; font-weight: 600; }
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
.gate-wrap { max-width: 980px; margin: 0 auto; }
.gate-logo { margin: 18px 0 2px; }
.gate-logo svg { height: 38px; width: auto; }
.gate-tagline {
  font-family: Georgia, "Iowan Old Style", serif;
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
  min-height: 146px;
}
.gate-name { font-family: Georgia, serif; font-size: 1.1rem; font-weight: 700; margin: 0; }
.gate-head { margin: 2px 0 8px; font-size: var(--fs-md); }
.gate-meta { color: var(--fin-muted); font-size: var(--fs-sm); margin: 0 0 10px; }
.gate-nums {
  display: flex; gap: 14px; margin: 0; font-size: var(--fs-sm); color: var(--fin-muted);
  font-variant-numeric: tabular-nums lining-nums;
  border-top: 1px solid var(--fin-line); padding-top: 8px;
}
.gate-nums b { color: var(--fin-ink); font-weight: 650; }
.gate-foot { color: var(--fin-muted); font-size: var(--fs-sm); margin: 22px 0 0; max-width: 72ch; }

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

/* Dark theme is token-level: every component already styles through the tokens,
   so redefining them here is the whole change. --fin-ink and --fin-paper were the
   gap before - near-black text and a near-white card ground both survived into
   dark mode because they were not tokenised. */
@media (prefers-color-scheme: dark) {
  :root {
  --fin-ink: #e7ebe6;
  --fin-muted: #9aa5a0;      /* 7.1:1 on #121714 */
  --fin-line: #333b37;
  --fin-accent: #5bbfa2;
  --fin-warn: #d2a248;
  --fin-paper: #1b211e;
  }
}
:root[data-theme="dark"] {
  --fin-ink: #e7ebe6;
  --fin-muted: #9aa5a0;      /* 7.1:1 on #121714 */
  --fin-line: #333b37;
  --fin-accent: #5bbfa2;
  --fin-warn: #d2a248;
  --fin-paper: #1b211e;
}
:root[data-theme="light"] {
  --fin-ink: #17211d;
  --fin-muted: #55605b;
  --fin-line: #e2ded4;
  --fin-accent: #1f6f5c;
  --fin-warn: #9a6a1b;
  --fin-paper: #fffefb;
}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(label: str, kind: str = "") -> str:
    cls = {"accent": "fin-chip fin-chip-accent", "warn": "fin-chip fin-chip-warn"}.get(kind, "fin-chip")
    return f'<span class="{cls}">{label}</span>'
