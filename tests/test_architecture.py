"""SPEC-000: the dependency rule, enforced as a build-time fitness function."""

from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAYERS = {"core": 0, "utils": 0, "rag": 1, "data": 1, "agents": 2, "workflow": 3,
          "web_app": 4, "mcp_server": 4}

# src.container is the composition root. It is not a layer: it imports from every
# layer by design, and only entry points import it. That invariant gets its own
# test below rather than being bent into the ordering.
COMPOSITION_ROOT = "src.container"
ENTRYPOINT_PREFIXES = ("src.web_app", "src.mcp_server")


def _layer(module: str) -> int | None:
    parts = module.split(".")
    if module == COMPOSITION_ROOT:
        return None
    if len(parts) >= 2 and parts[0] == "src":
        return LAYERS.get(parts[1])
    return None


def _modules():
    for path in (ROOT / "src").rglob("*.py"):
        rel = path.relative_to(ROOT).with_suffix("")
        yield ".".join(rel.parts), path


def test_no_upward_imports():
    """A module must never import from a layer above it.

    When this fails, fix the design - never the test. See copilot-instructions.md.
    """
    violations: list[str] = []
    for module, path in _modules():
        own = _layer(module)
        if own is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            for name in names:
                other = _layer(name)
                if other is not None and other > own:
                    violations.append(f"{module} (layer {own}) imports {name} (layer {other})")
    assert not violations, "upward imports found:\n  " + "\n  ".join(violations)


def test_core_imports_nothing_internal():
    bad: list[str] = []
    for module, path in _modules():
        if not module.startswith("src.core"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = ([node.module] if isinstance(node, ast.ImportFrom) and node.module else
                    [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for m in mods:
                if m.startswith("src.") and not m.startswith("src.core"):
                    bad.append(f"{module} imports {m}")
    assert not bad, "core must not depend on other layers:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("protocol", [
    "Embedder", "VectorIndex", "Retriever", "ChatProvider", "CacheBackend",
    "MarketDataProvider", "NewsProvider",
])
def test_protocols_have_two_impls(protocol):
    """A seam with one implementation is a guess; two makes it real."""
    impls = {
        "Embedder": ["LocalEmbedder", "OpenAIEmbedder", "HashingEmbedder"],
        "VectorIndex": ["NumpyIndex"],
        "Retriever": ["HybridRetriever", "DenseRetriever", "SparseRetriever"],
        "ChatProvider": ["LangChainChatProvider", "OfflineProvider", "FakeChatProvider"],
        "CacheBackend": ["SqliteCache", "MemoryCache", "NullCache"],
        "MarketDataProvider": ["YFinanceProvider", "MockProvider"],
        "NewsProvider": ["YFinanceNews", "RssNews", "MockNews"],
    }[protocol]
    source = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py"))
    source += (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    found = [name for name in impls if f"class {name}" in source]
    # NumpyIndex is the sole VectorIndex by design: at ~300 chunks an ANN index buys
    # nothing, and FaissIndex has no cp314 wheel. Documented in SPEC-001 non-goals.
    minimum = 1 if protocol == "VectorIndex" else 2
    assert len(found) >= minimum, f"{protocol} has only {found}"


def test_only_entrypoints_import_the_composition_root():
    """Wiring flows one way: entry points assemble, layers receive.

    A layer importing the container would be reaching for its own dependencies,
    which is exactly what the composition root exists to prevent.
    """
    offenders: list[str] = []
    for module, path in _modules():
        if module == COMPOSITION_ROOT or module.startswith(ENTRYPOINT_PREFIXES):
            continue
        text = path.read_text(encoding="utf-8")
        if f"from {COMPOSITION_ROOT} import" in text or f"import {COMPOSITION_ROOT}" in text:
            offenders.append(module)
    assert not offenders, ("only entry points may import the composition root; found: "
                           + ", ".join(offenders))
