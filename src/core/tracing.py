"""Langfuse tracing. Entirely optional, and silent when it fails.

Two rules govern everything here:

1. **Observability must never break answering.** Every call into Langfuse is
   wrapped; a tracing failure logs at debug and is swallowed. An app that 500s
   because its dashboard is down is worse than an app with no dashboard.
2. **Absent keys mean absent tracing, not a crash.** With no credentials the
   client is None, callbacks are an empty list, and spans are no-ops, so the
   app behaves identically — which is also what keeps `pytest` offline.

What it adds over the in-session cost meter: the meter lives in memory and dies
with the session. Langfuse answers "what did that question cost last Tuesday,
and which agent was slow".
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

_client: Any | None = None
_configured = False

# Shapes worth scrubbing before anything leaves the machine. This is NOT full
# PII redaction - see mask_payload's docstring.
_SECRET_PATTERNS = [
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{12,}", re.I),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b[0-9a-f]{32,}\b", re.I),
]


def pseudonym(value: str, prefix: str = "u") -> str:
    """Stable, non-reversible id. A persona id is synthetic, but sending raw
    identifiers to a third party is a habit worth not having."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def mask_payload(data: Any) -> Any:
    """Scrub obvious secrets from anything headed to Langfuse.

    KNOWN LIMIT, stated rather than papered over: this removes API-key shapes,
    email addresses, and long hex strings. It is NOT PII redaction - Fintor has
    no Presidio layer yet (Phase 3), so a user's free-text question reaches
    Langfuse substantially intact. Claiming "masked traces" when they are only
    partly masked would be worse than the gap. See the prompt-safety skill.
    """
    try:
        if isinstance(data, str):
            out = data
            for pattern in _SECRET_PATTERNS:
                out = pattern.sub("[redacted]", out)
            return out
        if isinstance(data, dict):
            return {k: mask_payload(v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return [mask_payload(v) for v in data]
    except Exception:  # noqa: BLE001 - masking must fail closed, not loudly
        return "[redacted: masking error]"
    return data


def configure(settings) -> Any | None:
    """Build the Langfuse client once. Returns None when unconfigured."""
    global _client, _configured
    if _configured:
        return _client
    _configured = True

    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.debug("Langfuse not configured; tracing disabled")
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url or None,
            mask=mask_payload,
            tracing_enabled=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse client unavailable: %s", exc)
        _client = None
    return _client


def client() -> Any | None:
    return _client


def enabled() -> bool:
    return _client is not None


def reset() -> None:
    """Test seam: forget the configured client."""
    global _client, _configured
    _client, _configured = None, False


def observability_callbacks() -> list[Any]:
    """LangChain callbacks for the provider call sites. Empty when disabled."""
    if _client is None:
        return []
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse callback handler unavailable: %s", exc)
        return []


@contextmanager
def trace_span(name: str, as_type: str = "span", **metadata: Any) -> Iterator[Any]:
    """Span around a unit of work. No-op when tracing is off, and it yields None
    rather than raising so call sites need no branching.

    Uses start_as_current_observation, NOT start_span: the latter creates a span
    without making it current, so nothing nests under it and get_current_trace_id
    returns None. The symptom was a log line reading "No active span in current
    context" and a null trace id on every turn.
    """
    if _client is None:
        yield None
        return
    try:
        with _client.start_as_current_observation(
            name=name, as_type=as_type, metadata=mask_payload(metadata)
        ) as span:
            yield span
        return
    except Exception as exc:  # noqa: BLE001 - tracing must never break answering
        logger.debug("span %s failed: %s", name, exc)
    yield None


def update_current_trace(**fields: Any) -> None:
    if _client is None:
        return
    try:
        _client.update_current_trace(**{k: mask_payload(v) for k, v in fields.items()})
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not update trace: %s", exc)


def current_trace_id() -> str | None:
    """Trace id for the AI Internals page, so the observability is on screen."""
    if _client is None:
        return None
    try:
        return _client.get_current_trace_id()
    except Exception:  # noqa: BLE001
        return None


def trace_url(trace_id: str | None, settings) -> str | None:
    if not trace_id or not settings.langfuse_base_url:
        return None
    return f"{settings.langfuse_base_url.rstrip('/')}/trace/{trace_id}"


def flush() -> None:
    """Send buffered events. Called at the end of a turn; never fatal."""
    if _client is None:
        return
    try:
        _client.flush()
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not flush traces: %s", exc)
