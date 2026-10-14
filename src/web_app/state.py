"""Shared Streamlit state and the cached container.

@st.cache_resource is load-bearing for cost: without it every rerun would rebuild
the embedder, reload the index, and re-open every cache. Cache layer 7.
"""

from __future__ import annotations

import asyncio
from typing import Any

import streamlit as st

from src.core.config import load_settings
from src.data import personas as persona_store


@st.cache_resource(show_spinner="Loading Fintor…")
def get_deps() -> Any:
    """One container per server process. Keyed by nothing: config is read once."""
    from src.container import build

    return build()


def settings():
    return get_deps().settings


def checkpoint_path() -> str:
    s = settings()
    return str(s.path(s.workflow.get("checkpoint_dir", "data/checkpoints"), "threads.sqlite"))


def active_persona():
    pid = st.session_state.get("persona_id", "maya")
    return persona_store.get(pid)


def run_async(coro):
    """Streamlit pages are sync; the workflow is async. One loop per interaction."""
    return asyncio.run(coro)


def record_turn(question: str, result: dict) -> None:
    key = f"turns::{st.session_state.get('persona_id','maya')}"
    st.session_state.setdefault(key, [])
    st.session_state[key].append({"q": question, "r": result})
    st.session_state["last_result"] = result
    st.session_state["last_question"] = question


def turns() -> list[dict]:
    return st.session_state.get(f"turns::{st.session_state.get('persona_id','maya')}", [])


def last_result() -> dict | None:
    return st.session_state.get("last_result")
