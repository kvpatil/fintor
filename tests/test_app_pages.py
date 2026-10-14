"""The app entry point actually runs.

These exist because a page-by-page probe missed a startup failure: two pages were
both backed by a callable named `render`, so Streamlit inferred the same URL for
each and st.navigation raised. Calling the page functions directly never touched
that, and an HTTP check could not see it either - Streamlit serves the same shell
for every path.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "web_app" / "app.py"


def _page_kwargs() -> list[dict[str, str]]:
    """Read every st.Page(...) call out of app.py without importing Streamlit."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    pages: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "Page"):
            continue
        kwargs = {kw.arg: kw.value.value for kw in node.keywords
                  if kw.arg and isinstance(kw.value, ast.Constant)}
        target = node.args[0] if node.args else None
        if isinstance(target, ast.Attribute):
            kwargs["_callable"] = target.attr
        pages.append(kwargs)
    return pages


def test_every_page_declares_an_explicit_url_path():
    """Inferred paths collide silently; explicit ones cannot."""
    pages = _page_kwargs()
    assert pages, "no st.Page(...) calls found in app.py"
    missing = [p.get("title", p.get("_callable", "?")) for p in pages if not p.get("url_path")]
    assert not missing, f"pages without an explicit url_path: {missing}"


def test_page_url_paths_are_unique():
    paths = [p["url_path"] for p in _page_kwargs()]
    duplicates = {p for p in paths if paths.count(p) > 1}
    assert not duplicates, f"duplicate url_path values: {sorted(duplicates)}"


def test_page_titles_are_unique():
    titles = [p.get("title", "") for p in _page_kwargs()]
    duplicates = {t for t in titles if titles.count(t) > 1}
    assert not duplicates, f"duplicate page titles: {sorted(duplicates)}"


@pytest.mark.slow
def test_app_entrypoint_runs_without_exception():
    """The check that would have caught the collision: run app.py as Streamlit does."""
    import os

    os.environ["FINTOR_OFFLINE"] = "1"
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=300)
    at.run()
    assert not at.exception, at.exception[0].value if at.exception else ""
    assert [t.value for t in at.title] == ["Ask Fintor"], "default page should be Chat"
