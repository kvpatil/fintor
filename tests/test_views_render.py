"""Every page renders, for every persona, without raising.

The suite was strong on logic and thin on the view layer - retriever 92%,
router 93%, but `views/workspace.py` at 12% and `views/internals.py` at 11%.
That gap matters more than the percentage suggests: a page that throws is a
blank screen, and nothing else here would catch it.

A NOTE ON HOW, because the obvious way does not work. Driving the real
`app.py` through AppTest and setting `query_params["page"]` does NOT navigate -
`st.navigation` ignores it, every test renders the default Chat page, and
coverage does not move at all. Measured: 21 such tests left views/about.py at
19%, exactly where it started. So each view function is invoked directly
through `AppTest.from_function`, which gives it a real script context without
the navigation layer in the way.

These are deliberately shallow - they are the smoke alarm that was missing,
not a substitute for the behavioural tests elsewhere.
"""

from __future__ import annotations

import os

import pytest

os.environ["FINTOR_OFFLINE"] = "1"

PERSONAS = ["maya", "dev", "priya", "walter", "aisha", "sam"]


def _render(view_module: str, fn_name: str, persona: str = "dev"):
    """Run one view function inside a real Streamlit script context.

    from_string rather than from_function: AppTest re-executes the function's
    SOURCE in a fresh module, so closures and default-argument references to
    outer names are not carried over and resolve to NameError.
    """
    from streamlit.testing.v1 import AppTest

    script = (
        "import streamlit as st\n"
        f"st.session_state['persona_id'] = {persona!r}\n"
        "from src.web_app.theme import inject\n"
        "inject()\n"
        f"import {view_module} as _v\n"
        f"_v.{fn_name}()\n"
    )
    at = AppTest.from_string(script, default_timeout=300)
    at.run()
    return at


def _ok(at, what: str) -> None:
    assert not at.exception, f"{what} raised: {at.exception[0].value}"
    drawn = (len(at.markdown) + len(at.title) + len(at.dataframe)
             + len(at.metric) + len(at.subheader) + len(at.caption))
    assert drawn > 0, f"{what} rendered nothing"


WORKSPACE = "src.web_app.views.workspace"
ABOUT = "src.web_app.views.about"


# --- the workspace, which was at 12% -------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("persona", PERSONAS)
def test_portfolio_renders_for_every_persona(persona):
    """Maya holds nothing at all, which is the empty-portfolio branch; the
    others have holdings of different shapes, which changes the allocation
    fold and whether a correlation matrix can be built."""
    _ok(_render(WORKSPACE, "portfolio", persona), f"portfolio as {persona}")


@pytest.mark.slow
@pytest.mark.parametrize("persona", ["maya", "walter"])
def test_goals_renders_for_contrasting_personas(persona):
    _ok(_render(WORKSPACE, "goals", persona), f"goals as {persona}")


@pytest.mark.slow
def test_market_renders():
    _ok(_render(WORKSPACE, "market"), "market")


# --- internals, which was at 11% -----------------------------------------


@pytest.mark.slow
def test_internals_renders_before_any_question_has_been_asked():
    """It reports on the last run. With no run yet it must say so rather than
    throw on a missing key."""
    at = _render("src.web_app.views.internals", "render")
    _ok(at, "internals with no prior turn")


# --- the about pages, which read real files off disk ---------------------


@pytest.mark.slow
@pytest.mark.parametrize("fn", ["architecture", "design", "governance", "recording"])
def test_about_pages_render(fn):
    """These read design.md, the SKILL.md set and specs/ off disk. A missing
    or malformed file should degrade, not crash."""
    _ok(_render(ABOUT, fn), f"about/{fn}")


# --- chat ----------------------------------------------------------------


@pytest.mark.slow
def test_chat_renders_the_journey_prompts_on_an_empty_transcript():
    at = _render("src.web_app.views.chat", "render")
    _ok(at, "chat")
    assert any("?" in b.label for b in at.button), \
        "no journey prompts offered on an empty transcript"


@pytest.mark.slow
def test_internals_renders_a_completed_turn():
    """With no prior turn the page returns early, which left two thirds of it
    unexecuted. Seeding a result exercises the parts that matter: the routing
    readout, the retrieval table with its fusion ranks, the model-call ledger
    and the guardrail counters.

    The shape mirrors what `stream_query` actually yields - if that contract
    changes, this breaks, which is the point.
    """
    from streamlit.testing.v1 import AppTest

    result = {
        "route": {"tier": "rules", "intents": ["portfolio"],
                  "reason": "rule signals matched",
                  "signals": {"portfolio": ["concentrated"]},
                  "advice_request": False},
        "final": {"text": "A grounded answer.", "citations_verified": 3,
                  "citations_stripped": ["[9]"],
                  "sections": [{"narration": "llm"}, {"narration": "template"}],
                  "data_status": "live"},
        "trace": [{"node": "guard", "ms": 0, "detail": "normalized; no block"},
                  {"node": "router", "ms": 1, "detail": "tier=rules"},
                  {"node": "agent:portfolio", "ms": 812, "detail": "3 citations"}],
        "agent_results": [{"agent": "portfolio", "chunks": [
            {"title": "Diversification", "difficulty": "beginner", "score": 0.71,
             "dense_rank": 1, "sparse_rank": 2, "rrf_score": 0.032,
             "retrieval": "hybrid"},
        ]}],
    }
    script = (
        "import streamlit as st\n"
        "st.session_state['persona_id'] = 'dev'\n"
        f"st.session_state['last_result'] = {result!r}\n"
        "from src.web_app.theme import inject\n"
        "inject()\n"
        "import src.web_app.views.internals as _v\n"
        "_v.render()\n"
    )
    at = AppTest.from_string(script, default_timeout=300)
    at.run()
    _ok(at, "internals with a completed turn")
    body = " ".join(m.value for m in at.markdown)
    assert "rules" in body or any("rules" in str(m.value) for m in at.metric)
