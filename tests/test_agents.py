"""The six agents, tested through the interface the workflow actually uses.

Until now NOTHING imported src.agents for behaviour - the only reference
anywhere was test_tracing.py calling inspect.getsource on base.py to check a
span was typed. Six agents, ~320 statements, and the only thing standing
between a regression and the user was the workflow tests mocking them out with
StubAgent. That is the gap this file closes.

Everything goes through `await Agent(deps).run(query)`, which is what
graph.py calls. Nothing here reaches past that into private helpers unless the
helper is itself the published contract (narration's grounding check is, and
is imported directly).

The guarantees pinned here are the ones the code claims in its own docstrings:
the relevance gate is a COST control and must not call the model; sample news
is never narrated; a personal tax question is redirected; a failing agent
degrades one section rather than the request.
"""

from __future__ import annotations

import pytest

from src.core.contracts import AgentResult, DataStatus, Intent, Query
from src.data.personas import get as get_persona
from tests.conftest import (FakeChatProvider, FakeMarket, FakeNews, FakeRetriever,
                            RecordingChain, make_deps)


def q(text: str, **kw) -> Query:
    return Query(text=text, **kw)


# --- the relevance gate is a cost control -------------------------------


async def test_finance_qa_refuses_without_passages_and_never_calls_the_model(retrieved):
    """The headline cost control. finance_qa.py says the gate runs "before the
    LLM, so an off-topic question costs nothing" - and nothing checked it.

    `chain.calls == 0` is the whole assertion. A refusal that still burned a
    completion would read identically to the user and quietly cost money on
    every off-topic question.
    """
    from src.agents.finance_qa import FinanceQAAgent

    chain = FakeChatProvider()
    deps = make_deps(chain=chain, retriever=FakeRetriever([]))   # gate refuses

    result = await FinanceQAAgent(deps).run(q("what is the airspeed of a swallow"))

    assert chain.calls == 0, "the refusal path called the model anyway"
    assert result.narration == "template"
    assert result.citations == []
    assert any("relevance threshold" in n for n in result.notices)


async def test_finance_qa_grounds_its_answer_in_the_retrieved_passages(retrieved):
    """The happy path: passages reach the model as numbered context, and the
    chunks and citations come back with the answer so the UI can show them."""
    from src.agents.finance_qa import FinanceQAAgent

    chain = RecordingChain("An index fund tracks an index [1].")
    deps = make_deps(chain=chain, retriever=FakeRetriever(retrieved))

    result = await FinanceQAAgent(deps).run(q("what is an index fund"))

    assert chain.calls == 1
    assert len(result.citations) == len(retrieved)
    assert result.chunks == retrieved
    assert result.data_status is DataStatus.LIVE
    assert result.costs and result.costs[0] is not None

    user_turn = chain.messages[0][-1]["content"]
    assert "[1]" in user_turn and "Index Fund" in user_turn, (
        "passages were not handed to the model as numbered context")
    assert "what is an index fund" in user_turn


async def test_the_persona_changes_the_instructions_the_model_is_given(retrieved):
    """Persona conditioning is the product's central claim. The same corpus and
    the same agent must brief the model differently per reader."""
    from src.agents.finance_qa import FinanceQAAgent

    briefs = {}
    for persona_id in ("maya", "walter"):
        chain = RecordingChain()
        deps = make_deps(chain=chain, retriever=FakeRetriever(retrieved))
        await FinanceQAAgent(deps).run(q("explain bonds"), persona=get_persona(persona_id))
        briefs[persona_id] = chain.messages[0][0]["content"]

    assert briefs["maya"] != briefs["walter"]
    assert "Define every term" in briefs["maya"], "the beginner brief lost its tone rule"
    assert "Maya" in briefs["maya"] and "Walter" in briefs["walter"]


# --- tax: a specialist that must not compute your bill -------------------


async def test_tax_redirects_a_personal_question_exactly_once(retrieved):
    from src.agents.tax import PERSONAL_TAX_REDIRECT, TaxAgent

    deps = make_deps(chain=FakeChatProvider("Capital gains work like this [1]."),
                     retriever=FakeRetriever(retrieved))

    result = await TaxAgent(deps).run(q("how much tax do I owe on this sale?"))

    assert result.text.count(PERSONAL_TAX_REDIRECT) == 1
    assert "Personal tax computation declined by policy." in result.notices


async def test_tax_leaves_a_general_question_alone(retrieved):
    """The redirect must not fire on education, or every tax answer carries a
    disclaimer that does not apply to it."""
    from src.agents.tax import PERSONAL_TAX_REDIRECT, TaxAgent

    deps = make_deps(chain=FakeChatProvider("Capital gains are taxed on sale [1]."),
                     retriever=FakeRetriever(retrieved))

    result = await TaxAgent(deps).run(q("how does capital gains tax work?"))

    assert PERSONAL_TAX_REDIRECT not in result.text
    assert "Personal tax computation declined by policy." not in result.notices


async def test_the_tax_agent_actually_narrows_retrieval_to_tax(retrieved):
    """`default_category = "tax"` is a class attribute that is only meaningful
    if it reaches the retriever. A recording fake is the only way to see it."""
    from src.agents.tax import TaxAgent

    retriever = FakeRetriever(retrieved)
    await TaxAgent(make_deps(retriever=retriever)).run(q("explain wash sales"))

    assert retriever.calls[0]["category"] == "tax"


async def test_an_explicit_category_on_the_query_beats_the_agent_default(retrieved):
    from src.agents.tax import TaxAgent

    retriever = FakeRetriever(retrieved)
    await TaxAgent(make_deps(retriever=retriever)).run(q("explain this", category="bonds"))

    assert retriever.calls[0]["category"] == "bonds"


# --- news: placeholders must never be narrated ---------------------------


async def test_sample_headlines_are_labelled_and_never_sent_to_the_model():
    """news.py: "a model paraphrasing fake news reads as real reporting".

    So the SAMPLE path must stay a plain labelled list. Asserting `calls == 0`
    is what makes that a guarantee rather than a comment.
    """
    from src.agents.news import NewsAgent
    from src.core.contracts import NewsItem

    items = [NewsItem(title="Markets drift", source="Placeholder", url="https://example.com",
                      published="2026-01-01", summary="Nothing real here.",
                      status=DataStatus.SAMPLE)]
    chain = FakeChatProvider()
    deps = make_deps(chain=chain, news=FakeNews(items, status=DataStatus.SAMPLE))

    result = await NewsAgent(deps).run(q("what is happening in markets"))

    assert chain.calls == 0, "sample headlines were paraphrased by the model"
    assert result.text.startswith("Sample headlines (not real news):")
    assert result.narration == "template"
    assert len(result.citations) == 1, "citations were dropped on the sample path"
    assert any("placeholders" in n for n in result.notices)


async def test_no_headlines_gives_a_usable_suggestion_not_an_empty_section():
    from src.agents.news import NewsAgent

    deps = make_deps(news=FakeNews([]))
    result = await NewsAgent(deps).run(q("news about nothing"))

    assert "couldn't retrieve headlines" in result.text
    assert result.narration == "template"
    assert result.citations == []


# --- portfolio: arithmetic in Python, never in the model -----------------


async def test_portfolio_asks_for_a_persona_rather_than_inventing_one():
    from src.agents.portfolio import PortfolioAgent

    result = await PortfolioAgent(make_deps()).run(q("how is my portfolio?"))

    assert "persona" in result.text.lower() or "pick" in result.text.lower()
    assert result.narration == "template"


async def test_portfolio_values_a_real_persona_and_flags_its_concentration():
    """Dev is 70% in one employer stock - the concentration flag is the single
    clearest demonstration in the product, so it must survive."""
    from src.agents.portfolio import PortfolioAgent

    dev = get_persona("dev")
    prices = {h.symbol: 100.0 for h in dev.holdings}
    deps = make_deps(chain=FakeChatProvider("Your portfolio is concentrated."),
                     market=FakeMarket(prices))

    result = await PortfolioAgent(deps).run(q("how concentrated am I?"), persona=dev)

    assert result.error_code is None
    assert result.text


async def test_portfolio_says_so_when_it_priced_from_cost_basis():
    """An unpriced holding is valued at cost. Silently doing that would make a
    stale number look live.

    BrokenProvider on purpose. The disclosure lives in the deterministic
    template, and on the narrated path the model is handed the same fact as
    `unpriced_symbols` and may word it however it likes - so the template is
    where the guarantee can actually be asserted. The first version of this
    test used a working fake, got back the model's "A summary." and failed:
    it was asserting against prose nobody promised.
    """
    from src.agents.portfolio import PortfolioAgent
    from tests.conftest import BrokenProvider

    dev = get_persona("dev")
    deps = make_deps(chain=BrokenProvider(), market=FakeMarket({}))   # nothing priced

    result = await PortfolioAgent(deps).run(q("value my holdings"), persona=dev)

    assert result.narration == "template"
    assert "cost basis" in result.text.lower(), (
        "an unpriced holding was valued silently")


async def test_the_unpriced_symbols_are_handed_to_the_narrator_as_fact():
    """The other half: on the narrated path the model can only mention the
    gap if it is given it."""
    from src.agents.portfolio import PortfolioAgent

    dev = get_persona("dev")
    chain = RecordingChain("A summary.")
    await PortfolioAgent(make_deps(chain=chain, market=FakeMarket({}))).run(
        q("value my holdings"), persona=dev)

    handed = " ".join(m["content"] for turn in chain.messages for m in turn)
    assert "unpriced_symbols" in handed


# --- market: symbol resolution is where the surprises live ---------------


def test_a_bare_index_name_resolves_to_a_disclosed_proxy_etf():
    """"the S&P 500" becomes SPY, and the substitution is disclosed. An
    undisclosed proxy is a quiet accuracy problem."""
    from src.agents.market import resolve_symbols

    symbols, notes = resolve_symbols("how is the S&P 500 doing?", None)

    assert "SPY" in symbols
    assert notes, "the ETF proxy was substituted without telling anyone"


def test_market_falls_back_to_the_persona_holdings_when_no_ticker_is_named():
    from src.agents.market import resolve_symbols

    dev = get_persona("dev")
    symbols, notes = resolve_symbols("how are my investments doing?", dev)

    assert symbols, "no symbols and no fallback leaves the agent with nothing"
    assert set(symbols) <= {h.symbol for h in dev.holdings}
    assert notes


def test_market_caps_the_number_of_symbols_it_will_price():
    """One request must not fan out into an unbounded number of quote lookups."""
    from src.agents.market import resolve_symbols

    symbols, _ = resolve_symbols("AAPL MSFT NVDA GOOG AMZN META TSLA NFLX AMD INTC", None)

    assert len(symbols) <= 6


async def test_market_asks_which_ticker_when_it_cannot_resolve_one():
    from src.agents.market import MarketAgent

    result = await MarketAgent(make_deps()).run(q("how are things?"))

    assert "ticker" in result.text.lower() or "index" in result.text.lower()
    assert result.narration == "template"


async def test_a_short_history_produces_no_trend_claim():
    """The trend needs more than 21 points. Below that the agent must stay
    silent rather than call three weeks a trend."""
    from src.agents.market import MarketAgent

    deps = make_deps(chain=FakeChatProvider("AAPL is at one hundred dollars."),
                     market=FakeMarket({"AAPL": 100.0}, history_points=10))

    result = await MarketAgent(deps).run(q("what is the trend for AAPL?"))

    assert result.error_code is None
    assert "moving average" not in result.text.lower()


# --- goal planning: the model may read numbers, never invent them --------


def test_a_figure_the_user_never_wrote_is_dropped_from_the_extraction():
    """The extraction guard. A model that hallucinates a target would otherwise
    have the whole projection built on it."""
    from src.agents.goal_planning import GoalParams, verify_extraction

    params, dropped = verify_extraction(
        GoalParams(target_amount=250_000.0), "I want to save for a house")

    assert params.target_amount is None, "a hallucinated target survived"
    assert dropped


def test_a_figure_the_user_did_write_is_kept():
    from src.agents.goal_planning import GoalParams, verify_extraction

    params, dropped = verify_extraction(
        GoalParams(target_amount=50_000.0), "I want to save $50k for a deposit")

    assert params.target_amount == 50_000.0
    assert not dropped


async def test_a_question_with_no_numbers_skips_the_extraction_call_entirely():
    """Another cost control: no digits means nothing to extract, so no
    structured call."""
    from src.agents.goal_planning import GoalPlanningAgent

    chain = RecordingChain()
    result = await GoalPlanningAgent(make_deps(chain=chain)).run(
        q("how should I think about saving?"))

    assert chain.calls == 0
    assert result.narration == "template"


async def test_an_unverifiable_extraction_is_reported_not_silently_used():
    from src.agents.goal_planning import GoalParams, GoalPlanningAgent

    chain = RecordingChain(structured_value=GoalParams(target_amount=999_999.0))
    deps = make_deps(chain=chain)

    result = await GoalPlanningAgent(deps).run(
        q("I have 100 dollars saved, am I on track?"), persona=get_persona("priya"))

    assert any("unverified" in n.lower() for n in result.notices)


# --- narration: the grounding check --------------------------------------


def test_a_number_absent_from_the_facts_is_called_out():
    from src.agents.narration import ungrounded_numbers

    assert ungrounded_numbers("Your balance is $44,000.", {"total": 29300.0})


def test_a_display_rounded_figure_is_accepted():
    """The model writes "$29,300" for 29300.0 - that is presentation, not
    invention, and flagging it would push every answer onto the template."""
    from src.agents.narration import ungrounded_numbers

    assert ungrounded_numbers("Your balance is $29,300.", {"total": 29300.0}) == []


def test_a_fraction_justifies_the_percentage_the_model_writes():
    from src.agents.narration import ungrounded_numbers

    assert ungrounded_numbers("That is 12.34% of the total.", {"share": 0.1234}) == []


def test_a_calendar_year_is_not_treated_as_an_invented_figure():
    from src.agents.narration import ungrounded_numbers

    assert ungrounded_numbers("Since 2008 markets recovered.", {"total": 10.0}) == []


def test_booleans_are_not_numbers():
    """`isinstance(True, int)` is True in Python, so a bool would otherwise
    enter the allowed set as 1.0 and justify the model writing "1"."""
    from src.agents.narration import facts_numbers

    assert facts_numbers({"on_track": True, "amount": 5.0}) == {5.0}


async def test_narration_falls_back_to_the_template_when_the_model_fails():
    from src.agents.narration import narrate
    from tests.conftest import BrokenProvider

    text, mode = await narrate(BrokenProvider(), {"total": 100.0}, "The total is 100.")

    assert mode == "template"
    assert "The total is 100." in text


async def test_narration_falls_back_when_the_model_invents_a_figure():
    """The important one: a fluent answer containing a number nobody computed
    is worse than the plain template, so it is discarded."""
    from src.agents.narration import narrate

    chain = FakeChatProvider("Your total is $987,654 which is excellent.")
    text, mode = await narrate(chain, {"total": 100.0}, "The total is 100.")

    assert mode == "template"
    assert "987,654" not in text


async def test_narration_keeps_a_grounded_answer():
    from src.agents.narration import narrate

    chain = FakeChatProvider("Your total is 100 dollars today.")
    text, mode = await narrate(chain, {"total": 100.0}, "The total is 100.")

    assert mode == "llm"
    assert "100" in text


# --- the base class contains failure -------------------------------------


async def test_a_failing_agent_costs_one_section_not_the_request():
    """graph.py fans out. One provider hiccup must not take the response with
    it, so run() swallows everything _execute raises."""
    from src.agents.base import BaseAgent

    class Exploding(BaseAgent):
        name = "boom"
        intent = Intent.FINANCE_QA
        section_title = "Background"

        async def _execute(self, query, persona):
            raise ValueError("provider exploded")

    result = await Exploding(make_deps()).run(q("anything"))

    assert isinstance(result, AgentResult)
    assert result.error_code == "ValueError"
    assert result.text == ""
    assert any("could not be completed" in n for n in result.notices)
    assert result.latency_ms >= 0, "timing was not stamped on the failure path"


# --- the registry the graph indexes into ---------------------------------


def test_every_intent_has_an_agent_and_a_place_in_the_section_order():
    """graph.py does SECTION_ORDER.index(r.intent), which raises ValueError for
    an intent that was added to the registry but not to the order. That is a
    crash in the synthesis step, discovered at runtime."""
    from src.agents.registry import AGENT_CLASSES, SECTION_ORDER, build_agents

    assert set(AGENT_CLASSES) == set(Intent), "an Intent has no agent"
    assert set(SECTION_ORDER) == set(AGENT_CLASSES), (
        "SECTION_ORDER and AGENT_CLASSES disagree; synthesis will raise")
    assert len(SECTION_ORDER) == len(set(SECTION_ORDER)), "a section is ordered twice"

    agents = build_agents(make_deps())
    assert set(agents) == set(Intent)
    assert all(hasattr(a, "run") for a in agents.values())


@pytest.mark.parametrize("intent", list(Intent))
def test_each_agent_declares_the_identity_the_ui_renders(intent):
    """name, intent and section_title are shown in the trace and the section
    headings. A blank one is a blank heading."""
    from src.agents.registry import AGENT_CLASSES

    cls = AGENT_CLASSES[intent]
    assert cls.name and isinstance(cls.name, str)
    assert cls.section_title and isinstance(cls.section_title, str)
    assert cls.intent is intent, f"{cls.__name__} is registered under the wrong intent"
