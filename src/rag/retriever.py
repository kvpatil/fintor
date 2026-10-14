"""Hybrid retrieval: dense + BM25, fused by Reciprocal Rank Fusion.

Why RRF rather than blending scores: cosine similarity and BM25 relevance live on
different, un-normalizable scales, so any weighted sum needs arbitrary constants
that silently shift with the corpus. RRF only uses *rank*, which is comparable by
construction. The cosine is then recomputed on the fused set so the score shown to
the user still means something absolute - an RRF score says nothing about whether
the top hit is actually relevant.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from src.core.contracts import Citation, Difficulty, RetrievedChunk
from src.rag.categories import resolve as resolve_categories
from src.rag.index import NumpyIndex

_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
_STOP = {
    "a","an","and","are","as","at","be","but","by","can","do","does","for","from","had","has",
    "have","how","i","if","in","is","it","its","me","my","of","on","or","that","the","their",
    "then","there","these","this","to","was","what","when","which","who","why","will","with","you","your",
}

# A beginner must not be served advanced passages; an advanced reader may see everything.
_LADDER = {Difficulty.BEGINNER: 0, Difficulty.INTERMEDIATE: 1, Difficulty.ADVANCED: 2}


def tokenize(text: str) -> list[str]:
    """Hyphenated finance terms are indexed whole *and* split, so both
    "tax-exempt" and "exempt" find the passage."""
    out: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        if tok in _STOP or len(tok) < 2:
            continue
        out.append(tok)
        if "-" in tok:
            out.extend(p for p in tok.split("-") if p and p not in _STOP)
    return out


class SparseRetriever:
    """BM25 over chunk text. Catches exact terms - "401(k)", "maturity", a ticker -
    that a static embedding will not place near the query."""

    def __init__(self, chunks: Sequence[dict]) -> None:
        from rank_bm25 import BM25Okapi

        self._chunks = list(chunks)
        corpus = [tokenize(self._searchable(c)) for c in self._chunks]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    @staticmethod
    def _searchable(chunk: dict) -> str:
        """Title, aliases, and related terms are repeated to weight them above body
        prose - a crude but effective field boost with a single BM25 index."""
        m = chunk.get("metadata", {})
        return " ".join(
            [m.get("title", ""), m.get("title", ""), m.get("aliases", ""),
             m.get("related_terms", ""), m.get("category", ""), chunk.get("text", "")]
        )

    def rank(self, query: str, top_k: int) -> list[tuple[str, float]]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [(self._chunks[i]["id"], float(scores[i])) for i in order if scores[i] > 0]


class DenseRetriever:
    def __init__(self, index: NumpyIndex, embedder) -> None:
        self._index = index
        self._embedder = embedder

    def rank(self, query: str, top_k: int) -> list[tuple[str, float]]:
        vec = self._embedder.embed([query])[0]
        return self._index.search(vec, top_k)


class HybridRetriever:
    """Implements core.ports.Retriever."""

    def __init__(
        self,
        chunks: Sequence[dict],
        index: NumpyIndex,
        embedder,
        *,
        rrf_k: int = 60,
        overfetch: int = 20,
        score_threshold: float = 0.25,
        mode: str = "hybrid",
    ) -> None:
        self._by_id = {c["id"]: c for c in chunks}
        self._dense = DenseRetriever(index, embedder)
        self._sparse = SparseRetriever(chunks)
        self._rrf_k = rrf_k
        self._overfetch = overfetch
        self._threshold = score_threshold
        self._mode = mode
        self._index = index
        self._embedder = embedder

    def count(self) -> int:
        return len(self._by_id)

    @staticmethod
    def _eligible(chunk: dict, categories: tuple[str, ...] | None, ceiling: Difficulty | None) -> bool:
        meta = chunk.get("metadata", {})
        if categories and meta.get("category", "") not in categories:
            return False
        if ceiling is not None:
            raw = meta.get("difficulty")
            if not raw:
                return False
            try:
                level = _LADDER[Difficulty(raw)]
            except (ValueError, KeyError):
                return False
            if level > _LADDER[ceiling]:
                return False
        return True

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        *,
        category: str | None = None,
        difficulty_ceiling: Difficulty | None = None,
    ) -> list[RetrievedChunk]:
        if not self._by_id:
            raise RuntimeError("knowledge base is empty; run `python -m src.rag.build`")

        n = max(self._overfetch, top_k)
        dense = self._dense.rank(query, n) if self._mode in {"hybrid", "dense"} else []
        sparse = self._sparse.rank(query, n) if self._mode in {"hybrid", "sparse"} else []

        fused: dict[str, dict] = {}
        for label, ranked in (("dense", dense), ("sparse", sparse)):
            for rank, (cid, _score) in enumerate(ranked, start=1):
                entry = fused.setdefault(cid, {"rrf": 0.0, "via": [], "dense_rank": None, "sparse_rank": None})
                entry["rrf"] += 1.0 / (self._rrf_k + rank)
                entry["via"].append(label)
                entry[f"{label}_rank"] = rank

        if not fused:
            return []

        # Recompute true cosine on the fused set: RRF ranks, it does not measure.
        qvec = self._embedder.embed([query])[0]
        cosines = dict(self._index.search(qvec, self._index.count()))

        allowed = resolve_categories(category)
        out: list[RetrievedChunk] = []
        for cid, entry in fused.items():
            chunk = self._by_id.get(cid)
            if chunk is None or not self._eligible(chunk, allowed, difficulty_ceiling):
                continue
            meta = chunk.get("metadata", {})
            raw_diff = meta.get("difficulty")
            out.append(
                RetrievedChunk(
                    id=cid,
                    text=chunk.get("text", ""),
                    title=meta.get("title", ""),
                    category=meta.get("category", ""),
                    difficulty=Difficulty(raw_diff) if raw_diff in _LADDER_VALUES else None,
                    source_name=meta.get("source_name", ""),
                    source_url=meta.get("source_url", ""),
                    score=round(float(cosines.get(cid, 0.0)), 4),
                    dense_rank=entry["dense_rank"],
                    sparse_rank=entry["sparse_rank"],
                    rrf_score=round(entry["rrf"], 6),
                    retrieval="+".join(dict.fromkeys(entry["via"])),
                )
            )

        out.sort(key=lambda c: (-c.rrf_score, -c.score))
        # The gate: below threshold we return nothing, and the caller must not call
        # an LLM. Refusing is cheaper and more honest than generating.
        kept = [c for c in out if c.score >= self._threshold][:top_k]
        return kept


_LADDER_VALUES = {d.value for d in Difficulty}


def to_citations(chunks: Sequence[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            index=i,
            title=c.title or c.id,
            source_name=c.source_name,
            source_url=c.source_url,
            category=c.category,
            excerpt=(c.text[:240] + "...") if len(c.text) > 240 else c.text,
            score=c.score,
        )
        for i, c in enumerate(chunks, start=1)
    ]
