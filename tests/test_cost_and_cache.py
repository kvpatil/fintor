"""SPEC-004 acceptance criteria."""

from __future__ import annotations

import pytest

from src.core.cache import SqliteCache
from src.core.contracts import CacheTier
from src.core.cost import BudgetExceeded, CostMeter
from src.core.llm import OfflineProvider, ProviderChain
from tests.conftest import BrokenProvider, FakeChatProvider

MESSAGES = [{"role": "user", "content": "What is an HSA?"}]


@pytest.mark.asyncio
async def test_exact_cache_returns_without_provider_call(tmp_path):
    """AC1: a repeat request costs nothing and reports the tier that served it."""
    provider = FakeChatProvider()
    chain = ProviderChain([provider], CostMeter(1.0), SqliteCache(tmp_path / "llm.db"))

    first = await chain.complete(MESSAGES)
    second = await chain.complete(MESSAGES)

    assert provider.calls == 1, "the second identical request must not reach the provider"
    assert second.cost.cache_tier is CacheTier.EXACT
    assert second.cost.usd == 0.0
    assert second.text == first.text


@pytest.mark.asyncio
async def test_offline_mode_makes_no_network_calls():
    """AC2: the offline provider runs with sockets blocked and bills nothing."""
    meter = CostMeter(1.0)
    chain = ProviderChain([OfflineProvider("maya")], meter)
    result = await chain.complete(MESSAGES)
    assert result.cost.usd == 0.0
    assert result.cost.cache_tier is CacheTier.OFFLINE
    assert "offline mode" in result.text
    again = await chain.complete(MESSAGES)
    assert again.text == result.text, "offline must be deterministic for reproducible demos"


@pytest.mark.asyncio
async def test_budget_guard_blocks_when_ceiling_exceeded():
    """AC3: the guard fires before the call, so no spend occurs."""
    provider = FakeChatProvider()
    meter = CostMeter(0.0)
    chain = ProviderChain([provider], meter)
    with pytest.raises(BudgetExceeded) as err:
        await chain.complete(MESSAGES)
    assert provider.calls == 0, "the provider must not be called once the budget is gone"
    assert "FINTOR_OFFLINE" in str(err.value), "the message should say how to keep working"


@pytest.mark.asyncio
async def test_provider_fallback_on_primary_failure():
    """AC5: a primary outage degrades to the next provider and records it."""
    broken, healthy = BrokenProvider(), FakeChatProvider("answer from fallback")
    chain = ProviderChain([broken, healthy], CostMeter(1.0))
    result = await chain.complete(MESSAGES)
    assert result.text == "answer from fallback"
    assert result.cost.fallback_used is True
    assert broken.calls == 1 and healthy.calls == 1


def test_cache_hit_is_still_metered():
    """A saving nobody can measure is a saving nobody believes."""
    from src.core.cost import price_call

    rec = price_call(provider="openai", model="gpt-4o-mini", input_tokens=500,
                     output_tokens=200, prices_per_mtok={"input": 0.15, "output": 0.60},
                     cache_tier=CacheTier.EXACT)
    assert rec.usd == 0.0
    assert rec.input_tokens == 500, "token counts are kept so savings are visible"
