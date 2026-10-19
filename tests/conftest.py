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


# --- fakes for the agent layer ------------------------------------------
#
# These lived inline in test_workflow.py as StubMarket/StubDeps. They are
# here because the agent tests need the same shapes, and a second copy is how
# a fake drifts from the port it stands in for. tests/test_architecture.py
# asserts each of these satisfies its Protocol in src/core/ports.py, which is
# what stops that drift silently.


class FakeRetriever:
    """Returns canned chunks and RECORDS how it was asked.

    The recording is the point for the tax agent: `default_category="tax"` is a
    class attribute that is supposed to reach `retrieve(category=...)`, and
    nothing else proves it does.
    """

    def __init__(self, chunks=None) -> None:
        self._chunks = list(chunks or [])
        self.calls: list[dict] = []

    def retrieve(self, text, *, top_k=6, category=None, difficulty_ceiling=None):
        self.calls.append({"text": text, "top_k": top_k, "category": category,
                           "difficulty_ceiling": difficulty_ceiling})
        return list(self._chunks)


class FakeMarket:
    """quotes() returns a dict, history() a tuple - the real asymmetry.

    MarketService.history returns `(rows, status)` and agents unpack it; a fake
    that returned a bare list would pass its own test and fail the real one.
    """

    def __init__(self, prices=None, history_points: int = 40, status=None) -> None:
        from src.core.contracts import DataStatus

        self._prices = dict(prices or {})
        self._points = history_points
        self.last_status = status or DataStatus.LIVE
        self.quote_calls: list[list[str]] = []

    def quotes(self, symbols):
        from src.core.contracts import DataStatus, Quote

        self.quote_calls.append(list(symbols))
        return {
            s: Quote(symbol=s, price=self._prices[s], change_pct=1.5,
                     currency="USD", provider="fake", status=DataStatus.LIVE)
            for s in symbols if s in self._prices
        }

    def history(self, symbol, period="6mo"):
        rows = [(f"2026-01-{i % 28 + 1:02d}", 100.0 + i) for i in range(self._points)]
        return rows, self.last_status


class FakeNews:
    def __init__(self, items=None, status=None) -> None:
        from src.core.contracts import DataStatus

        self._items = list(items or [])
        self.last_status = status or DataStatus.LIVE
        self.calls = 0

    def search(self, text, limit=5):
        self.calls += 1
        return list(self._items)[:limit]


class RecordingChain(FakeChatProvider):
    """Captures the messages it was handed, and can return a chosen object
    from `structured()`.

    FakeChatProvider.structured returns an EMPTY schema instance, which is only
    the "the model extracted nothing" case. Verifying the extraction guard
    needs a model that returns populated - and hallucinated - values.
    """

    def __init__(self, text: str = "fake answer", structured_value=None) -> None:
        super().__init__(text)
        self.messages: list = []
        self._structured_value = structured_value

    async def complete(self, messages, *, max_tokens=None):
        self.messages.append(messages)
        return await super().complete(messages, max_tokens=max_tokens)

    async def structured(self, schema, messages):
        self.messages.append(messages)
        self.calls += 1
        if self._structured_value is not None:
            return self._structured_value
        return schema()


def make_deps(*, chain=None, retriever=None, market=None, news=None, settings=None):
    """A duck-typed container. Nothing isinstance-checks deps, so this is enough."""

    class _Deps:
        pass

    deps = _Deps()
    deps.chain = chain if chain is not None else FakeChatProvider()
    deps.retriever = retriever if retriever is not None else FakeRetriever()
    deps.market = market if market is not None else FakeMarket()
    deps.news = news if news is not None else FakeNews()
    deps.settings = settings if settings is not None else type(
        "S", (), {"news": {"limit": 5}, "workflow": {"agent_timeout_seconds": 5}})()
    return deps


@pytest.fixture
def deps():
    return make_deps()


@pytest.fixture
def retrieved():
    """Two chunks in the shape the retriever really returns."""
    from src.core.contracts import RetrievedChunk

    return [
        RetrievedChunk(id="a#0", text="An index fund tracks an index at low cost.",
                       title="Index Fund", category="financial_basics",
                       difficulty="beginner", source_name="SEC Investor.gov",
                       source_url="https://investor.gov", score=0.81),
        RetrievedChunk(id="b#0", text="Capital gains are taxed when you sell.",
                       title="Capital Gains", category="tax",
                       difficulty="beginner", source_name="IRS",
                       source_url="https://irs.gov", score=0.74),
    ]
