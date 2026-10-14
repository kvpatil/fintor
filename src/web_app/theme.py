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

.fin-disclaimer {
  color: var(--fin-muted); font-size: 0.78rem; border-top: 1px solid var(--fin-line);
  padding-top: 8px; margin-top: 14px;
}
.fin-cite { font-size: 0.8rem; color: var(--fin-muted); }

@media (prefers-color-scheme: dark) {
  :root { --fin-line: #333b37; --fin-muted: #9aa5a0; }
  [data-testid="stMetric"], .fin-chip, .fin-persona { background: #1b211e; }
}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(label: str, kind: str = "") -> str:
    cls = {"accent": "fin-chip fin-chip-accent", "warn": "fin-chip fin-chip-warn"}.get(kind, "fin-chip")
    return f'<span class="{cls}">{label}</span>'


LOGO_SVG = """
<svg width="132" height="34" viewBox="0 0 132 34" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Fintor">
  <rect x="0" y="2" width="30" height="30" rx="8" fill="#1f6f5c"/>
  <text x="15" y="23" text-anchor="middle" font-family="Georgia,serif" font-size="16"
        font-weight="700" fill="#fbfaf7">Fi</text>
  <text x="38" y="23" font-family="Georgia,serif" font-size="19" font-weight="600" fill="#17211d">Fintor</text>
</svg>
"""
