"""Fintor — Streamlit entry point.

Run: streamlit run src/web_app/app.py
     FINTOR_OFFLINE=1 streamlit run src/web_app/app.py   # free, no network

Shape of this file: gate first, then navigation, then chrome, then the page. The
gate calls st.stop(), so none of the app's chrome exists until a persona is chosen
- which is what makes it read as a sign-in screen rather than a modal over the app.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# `streamlit run` puts this file's directory on sys.path, not the repo root, so
# absolute `src.` imports need the root added explicitly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.personas import PERSONAS  # noqa: E402
from src.web_app import chrome, gate  # noqa: E402
from src.web_app.brand import (  # noqa: E402
    favicon_data_uri, header_data_uri,
)
from src.web_app.theme import inject, is_dark  # noqa: E402
from src.web_app.views import about, chat, internals, workspace  # noqa: E402

st.set_page_config(page_title="Fintor", page_icon=favicon_data_uri(),
                   layout="wide", initial_sidebar_state="collapsed")
inject()

# --- the gate -----------------------------------------------------------
# Before navigation, so the tabs and header do not render behind the sign-in.
#
# A signed cookie is checked first. Without it a browser REFRESH logged the
# user out, because st.session_state lives and dies with the Streamlit
# session - measured: sign in, reload, back at the gate. The token is signed,
# so a hand-edited cookie cannot stand in for the password.
from src.web_app import session  # noqa: E402

# A sign-out on the previous run deferred its cookie clear to this one.
session.apply_pending()

if not st.session_state.get("persona_id"):
    session.restore({p.id for p in PERSONAS})

if not st.session_state.get("persona_id"):
    gate.render()
    st.stop()

# Signed in. Refresh the cookie if the browser does not already hold a current
# one - this cannot happen at sign-in time, because st.rerun() discards the
# render that would have carried the component.
session.sync(st.session_state["persona_id"])

# --- navigation ---------------------------------------------------------
# (section, title, url_path, render fn, icon)
#
# The four workspace pages carry "" as their section, which renders them FLAT and
# always visible in the top bar. The four reference pages share one section, which
# renders as a single labelled dropdown. A plain dict would make both groups
# dropdowns and bury About Fintor behind a click; nine flat tabs would crowd the
# row. url_path is explicit on every page because Streamlit otherwise infers it
# from the callable name, and two of these are both named `render`.
PAGE_SPEC: list[tuple[str, str, str, object, str]] = [
    ("", "Chat", "chat", chat.render, ":material/forum:"),
    ("", "Portfolio", "portfolio", workspace.portfolio, ":material/donut_small:"),
    ("", "Market", "market", workspace.market, ":material/trending_up:"),
    ("", "Goals", "goals", workspace.goals, ":material/flag:"),
    # AI Internals sits under About, not in the workspace row. It reports
    # routing tiers, retrieval ranks, cache layers and a token ledger - the
    # engineering story, which belongs with the other engineering pages. The
    # four workspace tabs are about the customer's money.
    ("About Fintor", "Architecture", "architecture", about.architecture, ":material/schema:"),
    ("About Fintor", "AI Internals", "internals", internals.render, ":material/memory:"),
    ("About Fintor", "Design Document", "design", about.design, ":material/description:"),
    ("About Fintor", "Governance", "governance", about.governance, ":material/policy:"),
    ("About Fintor", "Recording", "recording", about.recording, ":material/play_circle:"),
]

_pages: dict[str, list] = {}
_group_of: dict[object, str] = {}
for _section, _title, _path, _fn, _icon in PAGE_SPEC:
    _page = st.Page(_fn, title=_title, icon=_icon, url_path=_path,
                    default=_path == "chat")
    _pages.setdefault(_section, []).append(_page)
    # Keyed by object identity: url_path comes back empty for the default page, so
    # it cannot be used to look the group up again after navigation resolves.
    _group_of[_page] = _section

# The WORDMARK goes in icon_image, which is counter-intuitive and deliberate:
# with no sidebar Streamlit renders the icon_image slot, so passing the bare
# mark there meant the header showed a 24px glyph and the wordmark never
# appeared at all. Both slots get the lockup so either one is correct.
#
# Two files rather than one recoloured image: an <img> cannot inherit CSS
# colour. Known limit, same as the Plotly figures - Streamlit's theme menu
# repaints without rerunning the script, so the logo swaps one interaction
# after the toggle.
# The header wears the SAME supplied artwork as the login screen, minus the
# tagline. Two files because an <img> cannot inherit CSS colour.
#
# KNOWN LIMIT, unchanged from before: is_dark() is read when the script runs,
# and Streamlit repaints on a theme toggle WITHOUT rerunning - so the header
# logo is one interaction behind a toggle. The gate does not have this problem
# because it inlines both variants and swaps them in CSS; st.logo takes a
# single image, so the same trick is not available here.
_logo = header_data_uri(dark=is_dark())
st.logo(_logo, icon_image=_logo, size="large")

current = st.navigation(_pages, position="top")

# --- chrome, then the page ---------------------------------------------
chrome.header(_group_of.get(current, ""), current.title)
current.run()

# After the page body, not before: the dots report what this page just observed.
# Emitted earlier they would lag an interaction behind.
chrome.paint_nav_state()
