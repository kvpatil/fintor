"""Shared fixtures and fakes.

No test may call a paid API. A session fixture blocks outbound sockets so an
accidental network call fails loudly instead of billing - enforced rather than
merely requested. See .github/skills/llm-cost-discipline/SKILL.md.
"""

from __future__ import annotations

import os
import socket

import pytest

os.environ.setdefault("FINTOR_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")   # local model cache only

_real_socket = socket.socket


class _BlockedSocket(socket.socket):
    def connect(self, *a, **k):  # noqa: ANN002, ANN003
        raise AssertionError(
            "A test attempted a network connection. Tests must use fakes or recorded "
            "fixtures - see the llm-cost-discipline skill."
        )

    connect_ex = connect


@pytest.fixture(scope="session", autouse=True)
def _no_network():
    socket.socket = _BlockedSocket
    yield
    socket.socket = _real_socket


@pytest.fixture
def allow_local_sockets():
    """Opt out for tests that need loopback (none currently)."""
    socket.socket = _real_socket
    yield
    socket.socket = _BlockedSocket


# --- fakes --------------------------------------------------------------


class FakeChatProvider:
    """Counts invocations so a test can assert a cache prevented a call."""

    name = "openai"
    model = "gpt-4o-mini"

    def __init__(self, text: str = "fake answer") -> None:
        self.calls = 0
        self._text = text

    async def complete(self, messages, *, max_tokens=None):
        from src.core.cost import price_call
        from src.core.llm import Completion

        self.calls += 1
        return Completion(text=self._text, cost=price_call(
            provider=self.name, model=self.model, input_tokens=100, output_tokens=50,
            prices_per_mtok={"input": 0.15, "output": 0.60}))

    async def stream(self, messages, *, max_tokens=None):
        self.calls += 1
        yield self._text

    async def structured(self, schema, messages):
        self.calls += 1
        return schema()


class BrokenProvider(FakeChatProvider):
    async def complete(self, messages, *, max_tokens=None):
        self.calls += 1
        raise RuntimeError("primary provider down")


class FakeEmbedder:
    """Deterministic, dependency-free vectors."""

    def __init__(self, dim: int = 8) -> None:
        self._dim = dim

    @property
    def model_name(self) -> str:
        return f"fake-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts):
        import hashlib
        import math

        out = []
        for t in texts:
            vec = [0.0] * self._dim
            for tok in str(t).lower().split():
                h = int(hashlib.md5(tok.encode()).hexdigest()[:8], 16)
                vec[h % self._dim] += 1.0
            n = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / n for v in vec])
        return out


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def chunks():
    def mk(cid, title, text, category="financial_basics", difficulty="beginner"):
        return {"id": cid, "text": text,
                "metadata": {"title": title, "category": category, "difficulty": difficulty,
                             "source_name": "SEC Investor.gov", "source_url": "https://investor.gov",
                             "aliases": "", "related_terms": ""}}
    return [
        mk("a#0", "Index Fund", "Term: Index Fund. Definition: a fund tracking an index cheaply."),
        mk("b#0", "Maturity", "Term: Maturity. Definition: the date a bond repays face value.",
           category="bonds"),
        mk("c#0", "Duration", "Term: Duration. Definition: price sensitivity to interest rates.",
           category="bonds", difficulty="advanced"),
    ]
