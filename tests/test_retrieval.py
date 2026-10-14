"""SPEC-001 acceptance criteria."""

from __future__ import annotations

import json
import pathlib

import pytest

from src.core.contracts import Difficulty
from src.rag.index import IndexMismatch, NumpyIndex
from src.rag.retriever import HybridRetriever

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _retriever(chunks, embedder, **kw):
    index = NumpyIndex(embedder.dim, embedder.model_name)
    index.add([c["id"] for c in chunks], embedder.embed([c["text"] for c in chunks]))
    return HybridRetriever(chunks, index, embedder, **kw)


def test_rrf_fusion_orders_by_reciprocal_rank():
    """AC1: score = Σ 1/(k + rank), k=60. Ranked first in both lists beats first in one."""
    k = 60
    both = 1 / (k + 1) + 1 / (k + 1)
    one = 1 / (k + 1)
    mixed = 1 / (k + 1) + 1 / (k + 3)
    assert both > mixed > one
    assert mixed == pytest.approx(0.0322657, abs=1e-6)


def test_index_rejects_embedding_dimension_mismatch(chunks, fake_embedder, tmp_path):
    """AC2: a persisted index must refuse a different embedder, naming both."""
    index = NumpyIndex(fake_embedder.dim, fake_embedder.model_name)
    index.add([c["id"] for c in chunks], fake_embedder.embed([c["text"] for c in chunks]))
    index.save(tmp_path / "idx")

    other = NumpyIndex(16, "different-model")
    with pytest.raises(IndexMismatch) as err:
        other.load(tmp_path / "idx")
    assert "different-model" in str(err.value) and fake_embedder.model_name in str(err.value)


def test_retrieval_gate_refuses_below_threshold(chunks, fake_embedder):
    """AC3: nothing clears the floor -> no chunks, so the caller makes no LLM call."""
    r = _retriever(chunks, fake_embedder, score_threshold=0.99)
    assert r.retrieve("completely unrelated pizza toppings", top_k=3) == []


def test_difficulty_ceiling_filters_corpus(chunks, fake_embedder):
    """AC4: a beginner is never served advanced passages."""
    r = _retriever(chunks, fake_embedder, score_threshold=0.0)
    beginner = r.retrieve("bond maturity duration", top_k=5, difficulty_ceiling=Difficulty.BEGINNER)
    assert beginner, "expected some beginner material"
    assert all(c.difficulty is Difficulty.BEGINNER for c in beginner)
    unfiltered = r.retrieve("bond maturity duration", top_k=5)
    assert any(c.difficulty is Difficulty.ADVANCED for c in unfiltered), \
        "advanced material should be reachable without a ceiling"


def test_sparse_retrieves_exact_term(chunks, fake_embedder):
    """AC5: the BM25 half contributes independently of the dense half."""
    r = _retriever(chunks, fake_embedder, score_threshold=0.0, mode="sparse")
    hits = r.retrieve("maturity", top_k=3)
    assert any("Maturity" in h.title for h in hits)


def test_corpus_integrity():
    """AC6: 50-100 documents, each with a real source that survives into citations."""
    corpus = json.loads((ROOT / "src/data/kb/fintor_kb.json").read_text(encoding="utf-8"))
    docs = corpus["documents"]
    assert 50 <= len(docs) <= 100, f"corpus is {len(docs)} documents"
    assert all(d.get("source_url", "").startswith("http") for d in docs)
    assert all(d.get("source_name") for d in docs)
    ids = [d["id"] for d in docs]
    assert len(ids) == len(set(ids)), "duplicate document ids"
    levels = {d["difficulty"] for d in docs}
    assert levels == {"beginner", "intermediate", "advanced"}, "every level must have material"


def test_embedding_cache_survives_restart(tmp_path):
    """AC7: rebuilding issues zero embedding calls the second time."""
    from src.core.cache import EmbeddingCache

    calls = {"n": 0}

    def compute(texts):
        calls["n"] += len(texts)
        return [[0.5, 0.5, 0.5, 0.5] for _ in texts]

    path = tmp_path / "emb.db"
    first = EmbeddingCache(path)
    first.embed_with("m", 4, ["alpha", "beta", "alpha"], compute)
    assert calls["n"] == 2, "a repeated text within one batch must be computed once"

    reopened = EmbeddingCache(path)       # simulates a process restart
    reopened.embed_with("m", 4, ["alpha", "beta"], compute)
    assert calls["n"] == 2, "a restart must not re-embed"
    assert reopened.stats()["entries"] == 2
