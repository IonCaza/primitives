"""LangFuse observability for LLM / agent tracing.

Provides callback handlers and context propagation for LangChain/LangGraph
runs so every agent invocation appears as a structured trace in Langfuse.

OTel SDK setup (traces, metrics, logs) is handled via environment-based
auto-instrumentation (OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_SERVICE_NAME)
rather than programmatic setup, keeping this module focused on the
LangFuse integration layer.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_langfuse_available: bool | None = None


def langfuse_enabled() -> bool:
    """Return True when LangFuse env vars are configured."""
    global _langfuse_available
    if _langfuse_available is None:
        host = os.getenv("LANGFUSE_HOST", "")
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
        _langfuse_available = bool(host and public_key and secret_key)
        if _langfuse_available:
            logger.info("LangFuse enabled → %s", host)
        else:
            logger.info("LangFuse not configured — LLM tracing disabled")
    return _langfuse_available


def create_langfuse_handler() -> Any | None:
    """Build a LangFuse CallbackHandler for a LangChain/LangGraph run.

    Returns None when LangFuse is not configured.
    """
    if not langfuse_enabled():
        return None

    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        logger.debug("Failed to create LangFuse handler", exc_info=True)
        return None


def langfuse_propagate_attributes(
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_slug: str | None = None,
) -> Any:
    """Return a context manager that sets trace metadata on the current Langfuse span.

    Returns a no-op context manager when LangFuse is not configured.
    """
    if not langfuse_enabled():
        from contextlib import nullcontext

        return nullcontext()

    try:
        from langfuse import propagate_attributes

        kwargs: dict[str, Any] = {}
        if session_id:
            kwargs["session_id"] = session_id
        if user_id:
            kwargs["user_id"] = user_id
        if agent_slug:
            kwargs["trace_name"] = f"agent:{agent_slug}"
            kwargs["tags"] = [f"agent:{agent_slug}"]
            kwargs["metadata"] = {"agent_slug": agent_slug}
        return propagate_attributes(**kwargs)
    except Exception:
        logger.debug("Failed to build LangFuse propagation context", exc_info=True)
        from contextlib import nullcontext

        return nullcontext()
