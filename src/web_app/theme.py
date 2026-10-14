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
  --fin-muted: #5f6b66;
  --fin-line: #e2ded4;
  --fin-accent: #1f6f5c;
  --fin-warn: #9a6a1b;
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
  background: #fffefb;
}
[data-testid="stSidebar"] { border-right: 1px solid var(--fin-line); }

.fin-chip {
  display: inline-block; padding: 2px 9px; margin: 0 4px 4px 0;
  border: 1px solid var(--fin-line); border-radius: 999px;
  font-size: 0.74rem; color: var(--fin-muted); background: #fffefb;
  font-variant-numeric: tabular-nums;
}
.fin-chip-accent { border-color: var(--fin-accent); color: var(--fin-accent); }
.fin-chip-warn { border-color: var(--fin-warn); color: var(--fin-warn); }

.fin-persona {
  border: 1px solid var(--fin-line); border-left: 3px solid var(--fin-accent);
  border-radius: 8px; padding: 10px 12px; background: #fffefb; margin-bottom: 10px;
}
.fin-persona b { font-size: 0.96rem; }
.fin-persona span { color: var(--fin-muted); font-size: 0.8rem; }

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
  font-size: 0.74rem; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--fin-accent); margin: 10px 0 10px;
}
.gate-card {
  border: 1px solid var(--fin-line); border-radius: 8px;
  background: #fffefb; padding: 14px 15px 12px; margin-bottom: 8px;
  min-height: 146px;
}
.gate-name { font-family: Georgia, serif; font-size: 1.1rem; font-weight: 700; margin: 0; }
.gate-head { margin: 2px 0 8px; font-size: 0.9rem; }
.gate-meta { color: var(--fin-muted); font-size: 0.78rem; margin: 0 0 10px; }
.gate-nums {
  display: flex; gap: 14px; margin: 0; font-size: 0.76rem; color: var(--fin-muted);
  font-variant-numeric: tabular-nums lining-nums;
  border-top: 1px solid var(--fin-line); padding-top: 8px;
}
.gate-nums b { color: var(--fin-ink); font-weight: 650; }
.gate-foot { color: var(--fin-muted); font-size: 0.78rem; margin: 22px 0 0; max-width: 72ch; }

/* ---- top chrome ---- */
.bc { margin: 0; }
.bc ol { list-style: none; display: flex; flex-wrap: wrap; gap: 6px;
         margin: 0; padding: 0; font-size: 0.84rem; color: var(--fin-muted); }
.bc li { display: flex; gap: 6px; align-items: baseline; }
.bc-sep { color: var(--fin-line); }
.bc-now { color: var(--fin-ink); font-weight: 600; }

.ident { display: flex; align-items: baseline; justify-content: flex-end;
         gap: 8px; flex-wrap: wrap; }
.ident-who { font-size: 0.86rem; font-weight: 600; }
.ident-sub { color: var(--fin-muted); font-weight: 400; }

.chip, .chip-accent, .chip-warn {
  display: inline-block; padding: 1px 8px; border-radius: 999px;
  border: 1px solid var(--fin-line); background: #fffefb;
  font-size: 0.72rem; color: var(--fin-muted);
  font-variant-numeric: tabular-nums;
}
.chip-accent { border-color: var(--fin-accent); color: var(--fin-accent); }
.chip-warn { border-color: var(--fin-warn); color: var(--fin-warn); }

.chrome-rule { border-top: 1px solid var(--fin-line); margin: 10px 0 18px; }

.prompt-hint {
  font-size: 0.74rem; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--fin-muted); margin: 14px 0 6px;
}

.fin-disclaimer {
  color: var(--fin-muted); font-size: 0.78rem; border-top: 1px solid var(--fin-line);
  padding-top: 8px; margin-top: 14px;
}
.fin-cite { font-size: 0.8rem; color: var(--fin-muted); }

@media (prefers-color-scheme: dark) {
  :root { --fin-line: #333b37; --fin-muted: #9aa5a0; }
  [data-testid="stMetric"], .fin-chip, .fin-persona,
  .gate-card, .chip, .chip-accent, .chip-warn { background: #1b211e; }
}
:root[data-theme="dark"] {
  --fin-line: #333b37; --fin-muted: #9aa5a0;
}
:root[data-theme="dark"] [data-testid="stMetric"],
:root[data-theme="dark"] .fin-chip,
:root[data-theme="dark"] .fin-persona,
:root[data-theme="dark"] .gate-card,
:root[data-theme="dark"] .chip,
:root[data-theme="dark"] .chip-accent,
:root[data-theme="dark"] .chip-warn { background: #1b211e; }
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(label: str, kind: str = "") -> str:
    cls = {"accent": "fin-chip fin-chip-accent", "warn": "fin-chip fin-chip-warn"}.get(kind, "fin-chip")
    return f'<span class="{cls}">{label}</span>'
