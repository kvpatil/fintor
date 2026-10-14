# SPEC-001 — Knowledge base and hybrid retrieval

## Intent

Fintor answers education questions from a cited corpus rather than from model recall. This
spec defines the corpus, how it is embedded and indexed, and how a query is turned into a
ranked set of passages. Retrieval is hybrid — a dense vector half that captures meaning and a
BM25 sparse half that catches exact terms like "401(k)" or "maturity" — fused by Reciprocal
Rank Fusion. Below a relevance floor Fintor refuses rather than generating, which is both a
quality control and a cost control.

Personas narrow the corpus by difficulty: a beginner must not be served advanced passages.

## Contract

Implements `Embedder`, `VectorIndex`, and `Retriever` from `src/core/ports.py`. Returns
`RetrievedChunk` and `Citation` from `src/core/contracts.py`.

- `src/data/kb/fintor_kb.json` — the corpus, 60 documents.
- `src/rag/embedding.py` — `LocalEmbedder` (model2vec), `OpenAIEmbedder`, `HashingEmbedder`.
- `src/rag/index.py` — `NumpyIndex` (exact cosine) with model/dimension metadata.
- `src/rag/retriever.py` — `HybridRetriever`, `DenseRetriever`, `SparseRetriever`, RRF fusion.
- `src/rag/build.py` — chunk, embed, persist. Writes `src/data/kb/index/`.

## Acceptance criteria

1. Given known dense and sparse rankings, RRF produces the documented order using
   `score = Σ 1/(k + rank)` with `k = 60`.
2. Loading an index whose recorded embedding model or dimension differs from the active
   embedder raises `IndexMismatch` naming both, and does not return results.
3. When every candidate scores below `rag.score_threshold`, retrieval returns no chunks and
   the caller makes no LLM call.
4. A query issued with `difficulty_ceiling=BEGINNER` returns only chunks whose difficulty is
   beginner; with no ceiling, the full corpus is eligible.
5. A term appearing verbatim in a passage but semantically distant is still retrievable,
   proving the sparse half contributes independently of the dense half.
6. The corpus contains between 50 and 100 documents, and every document carries a
   `source_name` and `source_url` that survive into its `Citation`.
7. Building the index twice from unchanged input issues zero embedding provider calls on the
   second run.

## Edge cases

- An empty index is a different failure from a no-match: the former raises, the latter refuses.
- Chunking must not split mid-word; a chunk shorter than 20 characters is dropped.
- A document with no `source_url` is a corpus defect, caught at build time, not at query time.

## Non-goals

- No ANN index. At ~300 chunks, exact cosine over a 300×256 matrix is microseconds, and
  FAISS `IndexFlatIP` would perform the identical brute-force scan. `FaissIndex` can be added
  behind `VectorIndex` if the corpus grows by orders of magnitude.
- Cross-encoder reranking, HyDE, and multi-query expansion are Phase 2.

## Status

Draft — implementation follows this commit.
