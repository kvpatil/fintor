"""The index builder, which had no test at all.

`python -m src.rag.build` is how the committed index is produced, and the
index is committed precisely so nobody re-runs this on a clone - which is
exactly why it could rot unnoticed. A corpus edit that silently produced an
empty index would not be caught until retrieval started returning nothing.

The embedder is faked. Loading model2vec here would be slow and would want the
HF cache; what is under test is the BUILD - chunking, metadata flattening, the
corpus guard and the files written - not the embedding model.
"""

from __future__ import annotations

import json

import pytest

from src.rag import build


def _corpus(*docs) -> dict:
    return {"documents": list(docs)}


def _doc(doc_id="a", term="Index Fund", definition="A fund that tracks an index.", **kw):
    base = {"id": doc_id, "term": term, "definition": definition,
            "category": "financial_basics", "difficulty": "beginner",
            "source_name": "SEC Investor.gov", "source_url": "https://investor.gov"}
    base.update(kw)
    return base


@pytest.fixture
def built(tmp_path, monkeypatch, fake_embedder):
    """Run the real main() against a throwaway corpus and index directory."""
    corpus_path = tmp_path / "corpus.json"
    index_dir = tmp_path / "index"

    class _Settings:
        rag = {"chunk_chars": 1000, "chunk_overlap": 150, "index_dir": str(index_dir)}
        cache = {"dir": str(tmp_path / "cache")}

        def path(self, *parts):
            from pathlib import Path

            p = Path(*parts)
            p.parent.mkdir(parents=True, exist_ok=True)
            return p

    def _run(corpus: dict, argv_extra=()):
        corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
        monkeypatch.setattr(build, "load_settings", lambda: _Settings())
        monkeypatch.setattr(build, "build_embedder", lambda s, c: fake_embedder)
        monkeypatch.setattr(
            "sys.argv", ["build", "--corpus", str(corpus_path), *argv_extra])
        code = build.main()
        return code, index_dir

    return _run


# --- the pure helpers ----------------------------------------------------


def test_a_document_is_rendered_as_prose_not_json():
    """The embedder was trained on prose, and the LLM is later asked to cite
    the same shape - so the rendered form has to read as text."""
    text = build.render(_doc(example="VTI tracks the whole US market.",
                             aliases=["Tracker fund"], related_terms=["ETF"]))

    assert "Term: Index Fund" in text
    assert "Definition: A fund that tracks an index." in text
    assert "VTI tracks the whole US market." in text
    assert "Tracker fund" in text and "ETF" in text
    assert "{" not in text, "the document leaked through as JSON"


def test_text_that_fits_the_window_is_one_chunk():
    text = "A fund that tracks an index at low cost."     # 40 chars, over the floor
    assert build.chunk_text(text, size=1000, overlap=150) == [text]


def test_text_too_short_to_retrieve_yields_nothing_at_all():
    """The 20-char floor applies to the whole text, not just to trailing
    fragments. Worth stating: it means a degenerate document disappears from
    the index rather than ranking badly. render() always emits "Term: ...
    Definition: ..." so no real document hits this, but the rule is sharp and
    a future caller passing raw text would meet it.
    """
    assert build.chunk_text("A short definition.", size=1000, overlap=150) == []


def test_long_text_is_split_with_overlap_so_a_sentence_is_not_cut_in_half():
    text = " ".join(f"word{i}" for i in range(400))
    chunks = build.chunk_text(text, size=200, overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks), "a chunk exceeded the window"
    # Overlap means consecutive chunks share text; without it a term split
    # across the boundary is retrievable from neither side.
    assert any(chunks[i][-10:] in chunks[i + 1] or chunks[i + 1][:10] in chunks[i]
               for i in range(len(chunks) - 1))


def test_fragments_too_small_to_retrieve_are_dropped():
    """build.py: chunks under 20 chars "carry no retrievable signal and
    pollute the ranking"."""
    chunks = build.chunk_text("x" * 205, size=100, overlap=0)

    assert all(len(c) >= 20 for c in chunks)


# --- the build itself ----------------------------------------------------


def test_the_build_writes_an_index_and_its_records(built):
    code, index_dir = built(_corpus(_doc("a"), _doc("b", term="Maturity")))

    assert code == 0
    records = json.loads((index_dir / "records.json").read_text())
    assert len(records) == 2
    assert {r["id"] for r in records} == {"a#0", "b#0"}
    assert (index_dir / "index_meta.json").exists(), "the index metadata was not written"


def test_list_metadata_is_flattened_so_it_survives_the_round_trip(built):
    """aliases and related_terms arrive as lists and are stored as strings;
    a list here breaks the citation rendering downstream."""
    _code, index_dir = built(_corpus(
        _doc("a", aliases=["Tracker", "Passive fund"], related_terms=["ETF"])))

    meta = json.loads((index_dir / "records.json").read_text())[0]["metadata"]
    assert meta["aliases"] == "Tracker, Passive fund"
    assert meta["related_terms"] == "ETF"
    assert meta["title"] == "Index Fund", "the title is taken from the term"


def test_a_document_without_a_source_fails_the_build(built):
    """Every answer cites a source, so a document that cannot be cited is a
    build-time failure rather than a query-time surprise."""
    bad = _doc("a")
    del bad["source_url"]

    with pytest.raises(SystemExit) as excinfo:
        built(_corpus(bad))

    assert "source_url" in str(excinfo.value)
    assert "a" in str(excinfo.value), "the failure does not say which document"


def test_reset_clears_the_previous_index(built, tmp_path):
    _code, index_dir = built(_corpus(_doc("a"), _doc("b", term="Maturity")))
    stale = index_dir / "stale.json"
    stale.write_text("{}")

    built(_corpus(_doc("a")), argv_extra=("--reset",))

    assert not stale.exists(), "--reset left a file from the previous build"
    assert len(json.loads((index_dir / "records.json").read_text())) == 1


def test_the_built_index_can_actually_be_searched(built, fake_embedder):
    """The end that matters: build it, load it back, and find the document.

    Asserting the files exist proves only that something was written. This
    proves the vectors and the ids line up.
    """
    from src.rag.index import NumpyIndex

    _code, index_dir = built(_corpus(
        _doc("a", term="Index Fund", definition="A fund that tracks an index."),
        _doc("b", term="Maturity", definition="The date a bond repays face value.")))

    index = NumpyIndex(fake_embedder.dim, fake_embedder.model_name)
    index.load(index_dir)
    assert index.count() == 2

    hits = index.search(fake_embedder.embed(["the date a bond repays face value"])[0], k=2)
    assert hits, "the rebuilt index returned nothing"
    assert hits[0][0] == "b#0", "the planted document was not the top hit"
