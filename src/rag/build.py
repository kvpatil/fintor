"""Build the retrieval index from the corpus.

Run: python -m src.rag.build [--reset]

The output directory is committed to the repo on purpose. Re-embedding on every
clone or Cloud Run deploy would be a recurring cost for a static corpus.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.core.cache import EmbeddingCache
from src.core.config import load_settings
from src.rag.embedding import build_embedder
from src.rag.index import NumpyIndex

METADATA_KEYS = ("title", "category", "difficulty", "source_name", "source_url",
                 "aliases", "related_terms", "content_type", "group")


def render(doc: dict) -> str:
    """Template rather than raw JSON: the embedder sees prose, which is what it was
    trained on, and the LLM later sees the same shape it will be asked to cite."""
    parts = [f"Term: {doc['term']}", f"Definition: {doc['definition']}"]
    if doc.get("example"):
        parts.append(f"Example: {doc['example']}")
    if doc.get("aliases"):
        parts.append(f"Also called: {', '.join(doc['aliases'])}")
    if doc.get("related_terms"):
        parts.append(f"Related terms: {', '.join(doc['related_terms'])}")
    return "\n\n".join(parts)


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Character windows with word-boundary backtracking. Chunks under 20 chars are
    dropped - they carry no retrievable signal and pollute the ranking."""
    if len(text) <= size:
        return [text] if len(text) >= 20 else []
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + int(size * 0.65), end)
            if cut > start:
                end = cut
        piece = text[start:end].strip()
        if len(piece) >= 20:
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="discard the existing index first")
    ap.add_argument("--corpus", default="src/data/kb/fintor_kb.json")
    args = ap.parse_args()

    settings = load_settings()
    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    docs = corpus["documents"]

    missing = [d["id"] for d in docs if not d.get("source_url")]
    if missing:  # a corpus defect is a build-time failure, not a query-time surprise
        raise SystemExit(f"documents missing source_url: {missing}")

    cache = EmbeddingCache(settings.path(settings.cache.get("dir", "data/cache"), "embeddings.db"))
    embedder = build_embedder(settings, cache)

    size = int(settings.rag.get("chunk_chars", 1000))
    overlap = int(settings.rag.get("chunk_overlap", 150))

    chunks: list[dict] = []
    for di, doc in enumerate(docs):
        meta = {k: doc.get(k) for k in METADATA_KEYS if doc.get(k) is not None}
        meta["title"] = doc["term"]
        for key in ("aliases", "related_terms"):
            if isinstance(meta.get(key), list):
                meta[key] = ", ".join(meta[key])
        for ci, piece in enumerate(chunk_text(render(doc), size, overlap)):
            chunks.append({"id": f"{doc['id']}#{ci}", "text": piece,
                           "metadata": {**meta, "document_index": di, "chunk_index": ci}})

    index_dir = Path(settings.rag.get("index_dir", "src/data/kb/index"))
    if args.reset and index_dir.exists():
        for f in index_dir.glob("*"):
            f.unlink()

    vectors = embedder.embed([c["text"] for c in chunks])
    index = NumpyIndex(embedder.dim, embedder.model_name)
    index.add([c["id"] for c in chunks], vectors)
    index.save(index_dir)
    (index_dir / "records.json").write_text(json.dumps(chunks, indent=1))

    print(f"corpus:   {len(docs)} documents -> {len(chunks)} chunks")
    print(f"embedder: {embedder.model_name} ({embedder.dim}d)")
    print(f"embedded: {cache.api_calls} texts actually computed (rest served from cache)")
    print(f"index:    {index.count()} vectors at {index_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
