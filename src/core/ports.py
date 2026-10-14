"""Protocols for every external dependency.

Each Protocol below has at least two implementations. That is the point: a seam
with one implementation is a guess, while a seam with two is a seam that works -
and it is what lets the tests run with fakes instead of network calls.

Nothing here imports from a layer above `core`. See the dependency rule in
.github/copilot-instructions.md, enforced by test_no_upward_imports.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol, runtime_checkable

from src.core.contracts import (
    CostRecord,
    Difficulty,
    NewsItem,
    Quote,
    RetrievedChunk,
)


@runtime_checkable
class Embedder(Protocol):
    """Text -> vectors. Implementations: LocalEmbedder (model2vec), OpenAIEmbedder,
    HashingEmbedder (deterministic, offline, used by tests)."""

    @property
    def model_name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Must preserve input order and return unit-normalized vectors."""
        ...


@runtime_checkable
class VectorIndex(Protocol):
    """Dense nearest-neighbour store. Implementations: NumpyIndex (exact cosine),
    FaissIndex (optional, when a cp314 wheel exists).

    Implementations must persist `model_name` and `dim` alongside the vectors and
    refuse to load against a mismatched embedder - silently mixing vector spaces
    produces retrieval that looks fine and is wrong.
    """

    @property
    def dim(self) -> int: ...

    @property
    def model_name(self) -> str: ...

    def count(self) -> int: ...

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None: ...

    def search(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]:
        """Return (id, cosine) descending, length <= k."""
        ...

    def save(self, path: str) -> None: ...

    def load(self, path: str) -> None: ...


@runtime_checkable
class Retriever(Protocol):
    """Query -> ranked passages. Implementations: HybridRetriever (dense+BM25+RRF),
    DenseRetriever, SparseRetriever."""

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        *,
        category: str | None = None,
        difficulty_ceiling: Difficulty | None = None,
    ) -> list[RetrievedChunk]:
        """`difficulty_ceiling` is how personas narrow the corpus: a beginner must
        not be served advanced passages."""
        ...


class Completion(Protocol):
    """Minimal shape returned by ChatProvider, so callers never touch a vendor SDK type."""

    text: str
    cost: CostRecord


@runtime_checkable
class ChatProvider(Protocol):
    """LLM access. Implementations: OpenAIProvider, AnthropicProvider,
    OfflineProvider (canned, zero network), FakeChatProvider (tests, counts calls).

    Implementations must populate CostRecord on every call - including cache hits,
    where usd is 0 but the tier is recorded. An unmetered call is an unmanaged cost.
    """

    @property
    def name(self) -> str: ...

    async def complete(
        self, messages: Sequence[dict[str, str]], *, max_tokens: int | None = None
    ) -> Completion: ...

    async def stream(
        self, messages: Sequence[dict[str, str]], *, max_tokens: int | None = None
    ) -> AsyncIterator[str]: ...

    async def structured(
        self, schema: type, messages: Sequence[dict[str, str]]
    ) -> Any:
        """Must enforce the schema at the provider boundary so callers never parse prose."""
        ...


@runtime_checkable
class CacheBackend(Protocol):
    """Key-value cache with TTL. Implementations: SqliteCache, MemoryCache, NullCache.

    `get_stale` exists so a provider outage can serve a last-good value with an
    honest age rather than failing - see DataStatus.STALE.
    """

    def get(self, key: str, ttl_seconds: int) -> Any | None: ...

    def get_stale(self, key: str, max_age_seconds: int) -> tuple[Any, int] | None: ...

    def set(self, key: str, value: Any) -> None: ...

    def stats(self) -> dict[str, int]: ...


@runtime_checkable
class MarketDataProvider(Protocol):
    """Quotes and history. Implementations: YFinanceProvider, MockProvider.

    `supports` exists because coverage differs by provider (crypto pairs, for one),
    and the chain must skip rather than fail.
    """

    @property
    def name(self) -> str: ...

    def supports(self, symbol: str) -> bool: ...

    def quotes(self, symbols: Sequence[str]) -> list[Quote]: ...

    def history(self, symbol: str, period: str = "6mo") -> list[tuple[str, float]]: ...


@runtime_checkable
class NewsProvider(Protocol):
    """Headlines. Implementations: YFinanceNews, RssNews, MockNews.

    Returned text is untrusted third-party content - see the prompt-safety skill.
    """

    @property
    def name(self) -> str: ...

    def search(self, query: str, limit: int = 5) -> list[NewsItem]: ...
