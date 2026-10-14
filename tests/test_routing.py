"""SPEC-002 acceptance criteria."""

from __future__ import annotations

import pytest

from src.core.contracts import Intent, RouterTier
from src.workflow.router import Router, heuristic_route
from tests.conftest import FakeChatProvider, FakeEmbedder

CONFIDENT_CASES = [
    ("What is an index fund?", {Intent.FINANCE_QA}),
    ("How diversified is my portfolio?", {Intent.PORTFOLIO}),
    ("How is AAPL trading?", {Intent.MARKET}),
    ("How are capital gains taxed?", {Intent.TAX}),
    ("Any news on inflation?", {Intent.NEWS}),
    ("Am I on track for $200,000 in 5 years?", {Intent.GOAL_PLANNING}),
    ("What is the difference between an ETF and a mutual fund?", {Intent.FINANCE_QA}),
    ("What tax do I pay on my NVDA shares?", {Intent.TAX}),
]


@pytest.mark.parametrize("question,expected", CONFIDENT_CASES)
def test_router_tier1_regex_confident_cases(question, expected):
    """AC1: unambiguous questions resolve at tier 1, with no model call."""
    decision = heuristic_route(question)
    assert set(decision.intents) == expected
    assert decision.tier is RouterTier.RULES
    assert decision.confident is True


def test_compound_question_returns_both_intents_in_canonical_order():
    """AC2: two domains named -> two specialists, ordered for synthesis."""
    decision = heuristic_route("How are capital gains taxed and how is SPY doing?")
    assert set(decision.intents) == {Intent.MARKET, Intent.TAX}
    assert decision.intents.index(Intent.MARKET) < decision.intents.index(Intent.TAX)


def test_comparison_is_not_split_into_clauses():
    """"difference between X and Y" is one question; splitting it yields half-answers."""
    decision = heuristic_route("What is the difference between an ETF and a mutual fund?")
    assert decision.intents == [Intent.FINANCE_QA]


def test_ticker_inside_a_tax_question_is_not_a_price_lookup():
    decision = heuristic_route("What tax do I pay on my NVDA shares?")
    assert Intent.MARKET not in decision.intents


def test_advice_phrasing_sets_the_flag():
    """AC5: the flag is independent of which tier resolved the route."""
    assert heuristic_route("Should I buy more NVDA?").advice_request is True
    assert heuristic_route("What is an index fund?").advice_request is False


def test_empty_input_routes_to_finance_qa():
    for text in ("", "   ", "\n"):
        decision = heuristic_route(text)
        assert decision.intents == [Intent.FINANCE_QA]
        assert decision.confident is True


@pytest.mark.asyncio
async def test_router_escalates_to_tier3_when_ambiguous():
    """AC3: vague input that neither rules nor centroids resolve reaches the LLM tier."""

    class Classifier(FakeChatProvider):
        async def structured(self, schema, messages):
            self.calls += 1
            return schema(intents=["portfolio"], advice_request=False, reason="test")

    provider = Classifier()
    # A centroid threshold of 1.1 is unreachable, which forces tier 2 to decline.
    router = Router(embedder=FakeEmbedder(), chain=provider, centroid_threshold=1.1)
    decision = await router.route("my situation")
    assert decision.tier is RouterTier.LLM
    assert decision.intents == [Intent.PORTFOLIO]
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_router_falls_back_to_rules_when_llm_tier_raises():
    """AC4: routing never propagates an error - failing to route is not failing to answer."""

    class Exploding(FakeChatProvider):
        async def structured(self, schema, messages):
            self.calls += 1
            raise RuntimeError("classifier unavailable")

    router = Router(embedder=FakeEmbedder(), chain=Exploding(), centroid_threshold=1.1)
    decision = await router.route("my situation")
    assert decision.tier is RouterTier.LLM_FALLBACK_RULES
    assert decision.intents, "the rule result must still be usable"


@pytest.mark.asyncio
async def test_tier2_embedding_resolves_without_an_llm_call():
    """Tier 2 is free: when centroids are decisive, the LLM is never consulted."""

    class NeverCalled(FakeChatProvider):
        async def structured(self, schema, messages):
            raise AssertionError("tier 3 must not run when tier 2 is confident")

    # margin=0.0 too: the fake embedder cannot separate centroids, and the point
    # here is that a confident tier 2 skips tier 3 - not how the fake scores.
    router = Router(embedder=FakeEmbedder(), chain=NeverCalled(),
                    centroid_threshold=0.0, centroid_margin=0.0)
    decision = await router.route("my situation")
    assert decision.tier is RouterTier.EMBEDDING
