"""LLM access: OpenAI primary, Anthropic fallback, offline mode, all metered.

Three things happen on every call, in this order, and the order is the cost story:
  1. the budget guard runs    - refuse before spending, not after
  2. the exact cache is read  - a repeat question costs nothing
  3. the provider chain runs  - primary, then fallback, never a hard failure

See .github/skills/llm-cost-discipline/SKILL.md.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from src.core.cache import make_key
from src.core.config import Settings
from src.core.contracts import CacheTier, CostRecord, ModelTier
from src.core.cost import CostMeter, price_call
from src.core.tracing import observability_callbacks

OFFLINE_MODEL = "offline-canned"


@dataclass
class Completion:
    text: str
    cost: CostRecord


def _fingerprint(model: str, messages: Sequence[dict[str, str]], max_tokens: int | None) -> str:
    payload = json.dumps([model, list(messages), max_tokens], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- offline ------------------------------------------------------------


class OfflineProvider:
    """Deterministic canned responses. Zero network, zero spend, reproducible.

    Determinism matters twice over: tests need stable assertions, and a recorded
    demo needs the same answer on the second take.
    """

    name = "offline"

    def __init__(self, persona_id: str | None = None) -> None:
        self._persona_id = persona_id

    def _canned(self, messages: Sequence[dict[str, str]]) -> str:
        question = next((m["content"] for m in reversed(list(messages)) if m.get("role") == "user"), "")
        seed = int(hashlib.sha256(question.encode("utf-8")).hexdigest()[:8], 16)
        openers = [
            "Here is the short version, then the detail.",
            "The mechanics matter more than the maths here.",
            "Two things are going on, and they are easy to separate.",
        ]
        return (
            f"{openers[seed % len(openers)]}\n\n"
            f"[offline mode] This is a deterministic placeholder answer for: "
            f"“{question[:160]}”\n\n"
            "The retrieval, routing, fan-out, tool-calling, and cost-metering paths all ran "
            "normally to produce it — only the language model was replaced, so the workflow "
            "you see in AI Internals is the real one. Citations would appear as [1], [2] here."
        )

    async def complete(
        self, messages: Sequence[dict[str, str]], *, max_tokens: int | None = None
    ) -> Completion:
        text = self._canned(messages)
        return Completion(
            text=text,
            cost=price_call(
                provider=self.name,
                model=OFFLINE_MODEL,
                input_tokens=sum(len(m.get("content", "")) // 4 for m in messages),
                output_tokens=len(text) // 4,
                cache_tier=CacheTier.OFFLINE,
                persona_id=self._persona_id,
            ),
        )

    async def stream(
        self, messages: Sequence[dict[str, str]], *, max_tokens: int | None = None
    ) -> AsyncIterator[str]:
        text = self._canned(messages)
        for word in text.split(" "):
            yield word + " "

    async def structured(self, schema: type, messages: Sequence[dict[str, str]]) -> Any:
        """Offline structured output: the schema's own defaults. Every field in the
        structured-output models is optional precisely so this stays honest - we
        return "nothing extracted" rather than inventing plausible values."""
        return schema()


# --- hosted providers ---------------------------------------------------


class LangChainChatProvider:
    """Wraps ChatOpenAI / ChatAnthropic so callers never touch a vendor type."""

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        settings: Settings,
        *,
        tier: ModelTier = ModelTier.CHEAP,
        persona_id: str | None = None,
    ) -> None:
        self.name = provider
        self.model = model
        self._tier = tier
        self._persona_id = persona_id
        self._settings = settings
        cfg = settings.llm
        common = {
            "model": model,
            "temperature": cfg.get("temperature", 0.1),
            "timeout": cfg.get("timeout_seconds", 60),
            "max_retries": cfg.get("max_retries", 2),
            "max_tokens": cfg.get("max_output_tokens", 900),
        }
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            self._client = ChatOpenAI(api_key=api_key, **common)
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(api_key=api_key, **common)
        else:  # pragma: no cover - guarded by the chain builder
            raise ValueError(f"unknown provider {provider!r}")

    @staticmethod
    def _trace_config() -> dict[str, Any]:
        """Langfuse callbacks, or an empty list when tracing is off. Every LLM
        call goes through here so no call site can be left un-traced."""
        return {"callbacks": observability_callbacks()}

    @staticmethod
    def _as_lc(messages: Sequence[dict[str, str]]) -> list[tuple[str, str]]:
        role_map = {"system": "system", "user": "human", "assistant": "ai"}
        return [(role_map.get(m.get("role", "user"), "human"), m.get("content", "")) for m in messages]

    def _cost(self, msg: Any, started: float, *, fallback_used: bool) -> CostRecord:
        usage = getattr(msg, "usage_metadata", None) or {}
        cached = int((usage.get("input_token_details") or {}).get("cache_read", 0))
        return price_call(
            provider=self.name,
            model=self.model,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cached_input_tokens=cached,
            prices_per_mtok=self._settings.price(self.model),
            tier=self._tier,
            cache_tier=CacheTier.PROMPT if cached else CacheTier.MISS,
            latency_ms=int((time.perf_counter() - started) * 1000),
            persona_id=self._persona_id,
            fallback_used=fallback_used,
        )

    async def complete(
        self, messages: Sequence[dict[str, str]], *, max_tokens: int | None = None
    ) -> Completion:
        started = time.perf_counter()
        msg = await self._client.ainvoke(self._as_lc(messages), config=self._trace_config())
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        return Completion(text=text, cost=self._cost(msg, started, fallback_used=False))

    async def stream(
        self, messages: Sequence[dict[str, str]], *, max_tokens: int | None = None
    ) -> AsyncIterator[str]:
        async for chunk in self._client.astream(self._as_lc(messages),
                                                config=self._trace_config()):
            piece = chunk.content
            if isinstance(piece, str) and piece:
                yield piece

    async def structured(self, schema: type, messages: Sequence[dict[str, str]]) -> Any:
        """Schema enforced at the provider boundary, so callers never parse prose."""
        return await self._client.with_structured_output(schema).ainvoke(
            self._as_lc(messages), config=self._trace_config())


# --- the chain ----------------------------------------------------------


class ProviderChain:
    """Budget guard, then exact cache, then providers in order.

    A provider failure is not an error for the caller: the next provider answers and
    the CostRecord records fallback_used, which the AI Internals page surfaces.
    """

    def __init__(
        self,
        providers: Sequence[Any],
        meter: CostMeter,
        cache: Any | None = None,
        *,
        exact_ttl_seconds: int = 86400,
        persona_id: str | None = None,
    ) -> None:
        if not providers:
            raise ValueError("ProviderChain needs at least one provider")
        self._providers = list(providers)
        self._meter = meter
        self._cache = cache
        self._ttl = exact_ttl_seconds
        self._persona_id = persona_id

    @property
    def primary(self) -> Any:
        return self._providers[0]

    @property
    def offline(self) -> bool:
        return all(getattr(p, "name", "") == "offline" for p in self._providers)

    async def complete(
        self, messages: Sequence[dict[str, str]], *, max_tokens: int | None = None
    ) -> Completion:
        model = getattr(self.primary, "model", OFFLINE_MODEL)
        key = make_key("llm:exact", _fingerprint(model, messages, max_tokens))

        if self._cache is not None:
            hit = self._cache.get(key, self._ttl)
            if hit is not None:
                # Still metered, with usd == 0: a saving you cannot see is a saving
                # nobody believes.
                return Completion(
                    text=hit["text"],
                    cost=self._meter.record(
                        price_call(
                            provider=hit.get("provider", "cache"),
                            model=model,
                            input_tokens=hit.get("input_tokens", 0),
                            output_tokens=hit.get("output_tokens", 0),
                            cache_tier=CacheTier.EXACT,
                            persona_id=self._persona_id,
                        )
                    ),
                )

        if not self.offline:
            self._meter.check()  # refuse before spending

        last_error: Exception | None = None
        for position, provider in enumerate(self._providers):
            try:
                result = await provider.complete(messages, max_tokens=max_tokens)
            except Exception as exc:  # noqa: BLE001 - any provider error means "try the next"
                last_error = exc
                continue
            if position > 0:
                result.cost.fallback_used = True
            self._meter.record(result.cost)
            if self._cache is not None and result.text:
                self._cache.set(
                    key,
                    {
                        "text": result.text,
                        "provider": result.cost.provider,
                        "input_tokens": result.cost.input_tokens,
                        "output_tokens": result.cost.output_tokens,
                    },
                )
            return result

        raise RuntimeError(f"all providers failed; last error: {last_error}") from last_error

    async def stream(
        self, messages: Sequence[dict[str, str]], *, max_tokens: int | None = None
    ) -> AsyncIterator[str]:
        for provider in self._providers:
            try:
                async for piece in provider.stream(messages, max_tokens=max_tokens):
                    yield piece
                return
            except Exception:  # noqa: BLE001
                continue

    async def structured(self, schema: type, messages: Sequence[dict[str, str]]) -> Any:
        if not self.offline:
            self._meter.check()
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                return await provider.structured(schema, messages)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise RuntimeError(f"all providers failed on structured output: {last_error}") from last_error


def build_chain(
    settings: Settings,
    meter: CostMeter,
    cache: Any | None = None,
    *,
    tier: ModelTier = ModelTier.CHEAP,
    persona_id: str | None = None,
) -> ProviderChain:
    """Compose the chain from config. Offline wins over everything; absent keys are
    skipped rather than fatal, so the app runs with whatever is available."""
    if settings.offline:
        return ProviderChain([OfflineProvider(persona_id)], meter, None, persona_id=persona_id)

    providers: list[Any] = []
    for name in settings.llm.get("chain", ["openai", "anthropic"]):
        if not settings.has_provider(name):
            continue
        model = settings.model_for(tier.value, name)
        if not model:
            continue
        key = settings.openai_api_key if name == "openai" else settings.anthropic_api_key
        providers.append(
            LangChainChatProvider(name, model, key, settings, tier=tier, persona_id=persona_id)
        )

    if not providers:
        # No keys configured: degrade to offline rather than crash on first use.
        return ProviderChain([OfflineProvider(persona_id)], meter, None, persona_id=persona_id)

    return ProviderChain(
        providers,
        meter,
        cache,
        exact_ttl_seconds=settings.cache.get("llm_exact_ttl_seconds", 86400),
        persona_id=persona_id,
    )
