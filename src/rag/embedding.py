"""Embedders. Local by default, hosted on request, deterministic for tests.

All three go through EmbeddingCache, so a given (model, text) pair is embedded
once ever - the knowledge base costs nothing to rebuild. See the
llm-cost-discipline skill.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from src.core.cache import EmbeddingCache


def _normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else [0.0] * len(vec)


class LocalEmbedder:
    """model2vec static embeddings: numpy-only, no torch, free, offline-capable.

    Chosen over sentence-transformers because no cp314 torch wheel exists on this
    platform. The tradeoff is real - static embeddings carry less contextual nuance
    than a transformer encoder - and it is why the BM25 half of hybrid retrieval
    matters here rather than being decorative.
    """

    def __init__(self, model: str = "minishlab/potion-base-8M",
                 cache: EmbeddingCache | None = None,
                 source: str | None = None) -> None:
        """`model` is the IDENTITY; `source` is optionally where to load it from.

        They are separate because the committed index records the model name
        and `NumpyIndex.load` refuses a mismatch. Loading from a baked-in
        directory must therefore not change what the embedder calls itself,
        or every container would fail with IndexMismatch.

        `source` exists for containers. model2vec's `from_pretrained` defaults
        to `force_download=True`, so passing a repo id reaches HuggingFace on
        EVERY load - measured with a socket spy: one outbound connection even
        with a warm cache. Its loader short-circuits on a path that exists, so
        a local directory skips the network entirely and the container starts
        without depending on a third party being up.
        """
        import os

        from model2vec import StaticModel

        self._model_name = model
        origin = source or os.environ.get("FINTOR_LOCAL_MODEL", "").strip() or model
        self._model = StaticModel.from_pretrained(origin)
        self._dim = int(self._model.dim)
        self._cache = cache

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [_normalize(v.tolist()) for v in self._model.encode(list(texts))]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._cache is None:
            return self._encode(texts)
        return self._cache.embed_with(self._model_name, self._dim, texts, self._encode)


class OpenAIEmbedder:
    """text-embedding-3-small. Higher recall, costs money, needs a key."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small",
                 cache: EmbeddingCache | None = None) -> None:
        from langchain_openai import OpenAIEmbeddings

        self._model_name = model
        self._client = OpenAIEmbeddings(api_key=api_key, model=model)
        self._dim = 1536
        self._cache = cache

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [_normalize(v) for v in self._client.embed_documents(list(texts))]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._cache is None:
            return self._encode(texts)
        return self._cache.embed_with(self._model_name, self._dim, texts, self._encode)


class HashingEmbedder:
    """Deterministic hashed bag-of-words. No model download, no network, no cost.

    Exists so tests and a cold `FINTOR_OFFLINE=1` start never touch a model file.
    Retrieval quality is poor by design; it is a stand-in, not a recommendation.
    """

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def model_name(self) -> str:
        return f"hashing-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dim
            for token in text.lower().split():
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16)
                vec[h % self._dim] += 1.0
            out.append(_normalize(vec))
        return out


def build_embedder(settings, cache: EmbeddingCache | None = None):
    """Compose from config. Falls back to local when the OpenAI mode is requested
    without a key, rather than failing at first query."""
    mode = str(settings.rag.get("embeddings", "local")).lower()
    models = settings.rag.get("models", {})
    if mode == "openai" and settings.has_provider("openai"):
        return OpenAIEmbedder(settings.openai_api_key, models.get("openai", "text-embedding-3-small"), cache)
    return LocalEmbedder(models.get("local", "minishlab/potion-base-8M"), cache)
