"""Fintor — Streamlit entry point.

Run: streamlit run src/web_app/app.py
     FINTOR_OFFLINE=1 streamlit run src/web_app/app.py   # free, no network

Navigation is two groups via st.navigation's dict form: the Workspace a learner
uses, and About Fintor for the architecture, design document, governance
artifacts, and recording.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Running via `streamlit run` puts this file's directory on sys.path, not the repo
# root, so absolute `src.` imports need the root added explicitly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.web_app.pages import about, chat, internals, workspace  # noqa: E402
from src.web_app.theme import LOGO_SVG, inject  # noqa: E402

st.set_page_config(page_title="Fintor — finance, taught", page_icon="📘",
                   layout="wide", initial_sidebar_state="expanded")
inject()
st.sidebar.markdown(LOGO_SVG, unsafe_allow_html=True)
st.sidebar.caption("Educational only · not financial advice")

PAGES = {
    "Workspace": [
        st.Page(chat.render, title="Chat", icon=":material/forum:", default=True),
        st.Page(workspace.portfolio, title="Portfolio", icon=":material/donut_small:"),
        st.Page(workspace.market, title="Market", icon=":material/trending_up:"),
        st.Page(workspace.goals, title="Goals", icon=":material/flag:"),
        st.Page(internals.render, title="AI Internals", icon=":material/memory:"),
    ],
    "About Fintor": [
        st.Page(about.architecture, title="Architecture", icon=":material/schema:"),
        st.Page(about.design, title="Design Document", icon=":material/description:"),
        st.Page(about.governance, title="Governance", icon=":material/policy:"),
        st.Page(about.recording, title="Recording", icon=":material/play_circle:"),
    ],
}

st.navigation(PAGES).run()
