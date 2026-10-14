"""NumpyIndex: exact cosine over a dense matrix.

No ANN index here on purpose. At this corpus size the matrix is a few hundred rows,
so an exact dot product is microseconds - and FAISS IndexFlatIP, the index this
would otherwise use, performs exactly the same brute-force scan. The Protocol in
core.ports means a FaissIndex can be dropped in later without touching callers.

The index records which embedding model produced its vectors and refuses to load
against a different one. Silently mixing vector spaces yields retrieval that looks
plausible and is wrong, which is the worst available failure mode.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np


class IndexMismatch(RuntimeError):
    """Raised when a persisted index disagrees with the active embedder."""


class NumpyIndex:
    def __init__(self, dim: int, model_name: str) -> None:
        self._dim = dim
        self._model_name = model_name
        self._ids: list[str] = []
        self._matrix = np.zeros((0, dim), dtype=np.float32)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def count(self) -> int:
        return len(self._ids)

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        if not ids:
            return
        arr = np.asarray(vectors, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] != self._dim:
            raise IndexMismatch(f"expected vectors of dimension {self._dim}, got shape {arr.shape}")
        if not np.isfinite(arr).all():
            raise ValueError("non-finite values in embedding vectors")
        # Re-normalize defensively: cosine via dot product is only valid on unit vectors.
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix = np.vstack([self._matrix, arr / norms])
        self._ids.extend(ids)

    def search(self, vector: Sequence[float], k: int) -> list[tuple[str, float]]:
        if not self._ids:
            return []
        q = np.asarray(vector, dtype=np.float32)
        if q.shape[0] != self._dim:
            raise IndexMismatch(f"query dimension {q.shape[0]} != index dimension {self._dim}")
        n = np.linalg.norm(q)
        if n:
            q = q / n
        scores = self._matrix @ q
        k = min(k, len(self._ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(self._ids[i], float(scores[i])) for i in top]

    # -- persistence ---------------------------------------------------------
    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        np.save(p / "vectors.npy", self._matrix)
        (p / "index_meta.json").write_text(
            json.dumps({"model_name": self._model_name, "dim": self._dim, "ids": self._ids}, indent=1)
        )

    def load(self, path: str | Path) -> None:
        p = Path(path)
        meta_file = p / "index_meta.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"no index at {p}; run `python -m src.rag.build`")
        meta = json.loads(meta_file.read_text())
        if meta["model_name"] != self._model_name or int(meta["dim"]) != self._dim:
            raise IndexMismatch(
                f"index was built with {meta['model_name']} at dimension {meta['dim']}, "
                f"but the active embedder is {self._model_name} at dimension {self._dim}. "
                f"Rebuild with `python -m src.rag.build --reset`."
            )
        self._matrix = np.load(p / "vectors.npy").astype(np.float32)
        self._ids = list(meta["ids"])
        if self._matrix.shape[0] != len(self._ids):
            raise IndexMismatch("vector count does not match id count; index is corrupt, rebuild it")
