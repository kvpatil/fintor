"""Cache backends and the embedding cache.

Why a hand-rolled exact cache instead of LangChain's SQLiteCache + set_llm_cache:
that cache is transparent to the caller, so a hit is indistinguishable from a
miss. The AI Internals page has to report *which* layer served a response, and a
cache nobody can see is a cache nobody trusts. Same storage, explicit reporting.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
import threading
import time
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def make_key(*parts: str) -> str:
    """Stable across processes - deliberately not hash(), which is salted per run."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


class NullCache:
    """Implements CacheBackend by never storing. Used to prove a path is cache-free."""

    def get(self, key: str, ttl_seconds: int) -> Any | None:
        return None

    def get_stale(self, key: str, max_age_seconds: int) -> tuple[Any, int] | None:
        return None

    def set(self, key: str, value: Any) -> None:
        return None

    def stats(self) -> dict[str, int]:
        return {"hits": 0, "misses": 0, "entries": 0}


class MemoryCache:
    """In-process LRU. Fast path for tests and for per-run memoisation."""

    def __init__(self, max_entries: int = 2048) -> None:
        self._data: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max = max_entries
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get(self, key: str, ttl_seconds: int) -> Any | None:
        with self._lock:
            row = self._data.get(key)
            if row is None:
                self._misses += 1
                return None
            value, created = row
            if ttl_seconds and (time.time() - created) > ttl_seconds:
                self._misses += 1
                return None
            self._data.move_to_end(key)
            self._hits += 1
            return value

    def get_stale(self, key: str, max_age_seconds: int) -> tuple[Any, int] | None:
        with self._lock:
            row = self._data.get(key)
        if row is None:
            return None
        value, created = row
        age = int(time.time() - created)
        return (value, age) if age <= max_age_seconds else None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (value, time.time())
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"hits": self._hits, "misses": self._misses, "entries": len(self._data)}


class SqliteCache:
    """On-disk TTL cache. Survives restarts, which is the whole point: an in-memory
    cache would re-bill every `streamlit run`."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS kv ("
                " key TEXT PRIMARY KEY, value TEXT NOT NULL,"
                " created_at REAL NOT NULL, hit_count INTEGER NOT NULL DEFAULT 0)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(self, key: str, ttl_seconds: int) -> Any | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT value, created_at FROM kv WHERE key=?", (key,)).fetchone()
            if row is None:
                self._misses += 1
                return None
            value, created = row
            if ttl_seconds and (time.time() - created) > ttl_seconds:
                self._misses += 1
                return None
            conn.execute("UPDATE kv SET hit_count=hit_count+1 WHERE key=?", (key,))
            self._hits += 1
            return json.loads(value)

    def get_stale(self, key: str, max_age_seconds: int) -> tuple[Any, int] | None:
        """Last-good value during a provider outage. Callers must label it STALE."""
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT value, created_at FROM kv WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        value, created = row
        age = int(time.time() - created)
        return (json.loads(value), age) if age <= max_age_seconds else None

    def set(self, key: str, value: Any) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO kv(key, value, created_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, created_at=excluded.created_at",
                (key, json.dumps(value, default=str), time.time()),
            )

    def stats(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            (n,) = conn.execute("SELECT COUNT(*) FROM kv").fetchone()
        return {"hits": self._hits, "misses": self._misses, "entries": int(n)}


class EmbeddingCache:
    """Cache layer 4: the knowledge base is embedded once, ever.

    Vectors are stored as raw float32 blobs keyed by sha256(model||text). Rows whose
    blob length disagrees with the current dimension are skipped rather than
    reinterpreted - a stored 256-d vector is not a 1536-d vector with padding.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.api_calls = 0  # how many texts actually reached the provider
        self._lock = threading.Lock()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS emb ("
                " key TEXT PRIMARY KEY, model TEXT NOT NULL, dim INTEGER NOT NULL, vec BLOB NOT NULL)"
            )

    @staticmethod
    def _pack(vec: Sequence[float]) -> bytes:
        return struct.pack(f"<{len(vec)}f", *vec)

    @staticmethod
    def _unpack(blob: bytes) -> list[float]:
        return list(struct.unpack(f"<{len(blob) // 4}f", blob))

    def embed_with(self, model: str, dim: int, texts: Sequence[str], compute) -> list[list[float]]:
        """Return a vector per text, in order. `compute` is called only for misses,
        and only once per distinct text even if it repeats within the batch."""
        keys = [make_key(model, t) for t in texts]
        found: dict[str, list[float]] = {}
        with self._lock, sqlite3.connect(self._path) as conn:
            for key in set(keys):
                row = conn.execute("SELECT dim, vec FROM emb WHERE key=? AND model=?", (key, model)).fetchone()
                if row and int(row[0]) == dim and len(row[1]) == dim * 4:
                    found[key] = self._unpack(row[1])

        missing_idx = [i for i, k in enumerate(keys) if k not in found]
        if missing_idx:
            # Dedupe within the batch before calling out: identical chunks are common.
            uniq: dict[str, int] = {}
            for i in missing_idx:
                uniq.setdefault(texts[i], i)
            to_compute = list(uniq.keys())
            self.api_calls += len(to_compute)
            vectors = compute(to_compute)
            with self._lock, sqlite3.connect(self._path) as conn:
                for text, vec in zip(to_compute, vectors, strict=True):
                    key = make_key(model, text)
                    found[key] = list(vec)
                    conn.execute(
                        "INSERT INTO emb(key, model, dim, vec) VALUES(?,?,?,?) "
                        "ON CONFLICT(key) DO UPDATE SET vec=excluded.vec, dim=excluded.dim",
                        (key, model, dim, self._pack(vec)),
                    )
        return [found[k] for k in keys]

    def stats(self) -> dict[str, int]:
        with sqlite3.connect(self._path) as conn:
            (n,) = conn.execute("SELECT COUNT(*) FROM emb").fetchone()
        return {"entries": int(n), "api_calls": self.api_calls}
