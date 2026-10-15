"""Langfuse tracing: optional, silent on failure, and honest about its limits.

The failure mode worth testing is not "does it trace" — it is "does the app
still work when tracing is absent, broken, or slow". An app that breaks because
its dashboard is down is worse than an app with no dashboard.
"""

from __future__ import annotations

import pytest

from src.core import tracing


@pytest.fixture(autouse=True)
def _reset_tracing():
    tracing.reset()
    yield
    tracing.reset()


class _Settings:
    """Minimal stand-in; the real Settings is frozen and reads the environment."""

    def __init__(self, pub: str = "", sec: str = "", base: str = "") -> None:
        self.langfuse_public_key = pub
        self.langfuse_secret_key = sec
        self.langfuse_base_url = base


# --- disabled by default ------------------------------------------------


def test_tracing_is_off_without_keys():
    assert tracing.configure(_Settings()) is None
    assert tracing.enabled() is False
    assert tracing.observability_callbacks() == []


def test_spans_are_noops_when_disabled():
    """Call sites must not branch on whether tracing is on."""
    tracing.configure(_Settings())
    with tracing.trace_span("workflow.chat", persona="p_abc") as span:
        assert span is None
    tracing.update_current_trace(metadata={"anything": 1})
    tracing.flush()
    assert tracing.current_trace_id() is None


def test_partial_keys_do_not_enable_tracing():
    """A public key alone would fail at send time; better to stay off."""
    assert tracing.configure(_Settings(pub="pk-lf-x")) is None


# --- never breaks the request ------------------------------------------


def test_a_client_that_throws_does_not_escape():
    """Observability must never break answering."""

    class Exploding:
        def start_span(self, **_kw):
            raise RuntimeError("langfuse is down")

        def update_current_trace(self, **_kw):
            raise RuntimeError("langfuse is down")

        def get_current_trace_id(self):
            raise RuntimeError("langfuse is down")

        def flush(self):
            raise RuntimeError("langfuse is down")

    tracing._client = Exploding()
    with tracing.trace_span("workflow.chat") as span:
        assert span is None, "a failed span yields None rather than raising"
    tracing.update_current_trace(metadata={"x": 1})
    tracing.flush()
    assert tracing.current_trace_id() is None


def test_a_span_that_fails_to_end_is_swallowed():
    class BadSpan:
        def end(self):
            raise RuntimeError("end failed")

    class Client:
        def start_span(self, **_kw):
            return BadSpan()

    tracing._client = Client()
    with tracing.trace_span("agent.market"):
        pass  # the failing end() must not surface


# --- pseudonymisation ---------------------------------------------------


def test_pseudonym_is_stable_and_not_the_input():
    first = tracing.pseudonym("dev", "p")
    assert first == tracing.pseudonym("dev", "p")
    assert "dev" not in first.replace("p_", "", 1)
    assert first != tracing.pseudonym("walter", "p")
    assert first.startswith("p_")


# --- masking, and its documented limit ---------------------------------


@pytest.mark.parametrize("secret", [
    "sk-lf-abcdef0123456789abcd",
    "pk-proj-ABCDEFGHIJKLMNOPQRS",
    "user@example.com",
    "a3f5c9d10b2e4f6789abcdef01234567",
])
def test_mask_scrubs_secret_shapes(secret):
    assert secret not in tracing.mask_payload(f"here it is: {secret} ok")


def test_mask_recurses_through_structures():
    payload = {"messages": [{"content": "key sk-lf-abcdef0123456789abcd"}]}
    assert "sk-lf-" not in str(tracing.mask_payload(payload))


def test_mask_is_not_pii_redaction_and_we_do_not_claim_it_is():
    """A plain name or phone number survives. Fintor has no Presidio layer yet.

    This test exists to keep the gap visible: if someone later claims "traces are
    PII-masked", this failing expectation is where they will find out otherwise.
    """
    assert "Jane Doe" in tracing.mask_payload("my name is Jane Doe")
    limit = tracing.mask_payload.__doc__ or ""
    assert "NOT PII redaction" in limit, "the limit must stay documented in code"


# --- config -------------------------------------------------------------


def test_settings_reads_the_langfuse_base_url_name():
    """LANGFUSE_BASE_URL is the SDK's current name and the one in the user's .env;
    LANGFUSE_HOST stays accepted as the legacy spelling."""
    import inspect

    from src.core import config

    src = inspect.getsource(config)
    assert "LANGFUSE_BASE_URL" in src
    assert "LANGFUSE_HOST" in src, "legacy name should still be honoured"


def test_settings_does_not_leak_keys_in_repr():
    from src.core.config import Settings

    s = Settings(raw={}, langfuse_secret_key="sk-lf-supersecret",
                 langfuse_public_key="pk-lf-public")
    assert "supersecret" not in repr(s)


def test_trace_url_needs_both_id_and_base_url():
    assert tracing.trace_url(None, _Settings(base="https://x")) is None
    assert tracing.trace_url("abc", _Settings()) is None
    assert tracing.trace_url("abc", _Settings(base="https://x/")) == "https://x/trace/abc"


# --- every LLM call site is instrumented --------------------------------


def test_all_provider_call_sites_attach_callbacks():
    """complete / stream / structured must each pass the trace config, or a code
    path goes silently untraced."""
    import inspect

    from src.core.llm import LangChainChatProvider

    for method in ("complete", "stream", "structured"):
        src = inspect.getsource(getattr(LangChainChatProvider, method))
        assert "_trace_config()" in src, f"{method} is not traced"


def test_span_uses_the_context_propagating_api():
    """start_span() creates a span without making it CURRENT.

    Observed live: nothing nested under it, get_current_trace_id() returned None,
    and the SDK logged "No active span in current context". The fix is
    start_as_current_observation, and this pins it.
    """
    import inspect

    src = inspect.getsource(tracing.trace_span)
    assert "start_as_current_observation" in src
    assert "_client.start_span(" not in src, "start_span does not propagate context"


def test_observations_are_typed():
    """A chain, a span and an agent read differently in the Langfuse UI; typing
    them is what makes the trace legible rather than a flat list."""
    import inspect

    graph = inspect.getsource(__import__("src.workflow.graph", fromlist=["x"]))
    base = inspect.getsource(__import__("src.agents.base", fromlist=["x"]))
    assert 'as_type="chain"' in graph, "the workflow should be a chain"
    assert 'as_type="agent"' in base, "an agent run should be an agent observation"
