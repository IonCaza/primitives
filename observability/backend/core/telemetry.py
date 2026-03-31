"""OpenTelemetry and LangFuse instrumentation for a FastAPI backend.

Initialise early (before other app modules) so auto-instrumentation
monkey-patches SQLAlchemy, Redis, httpx, etc. before engines are created.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_initialized = False


# ── Bootstrap ─────────────────────────────────────────────────────────

def init_telemetry() -> None:
    """Set up OTel SDK providers and auto-instrument libraries.

    Safe to call multiple times; only the first call has effect.
    Silently no-ops when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
    """
    global _initialized
    if _initialized:
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — OpenTelemetry disabled")
        return

    try:
        _setup_providers(endpoint)
        _setup_auto_instrumentation()
        _initialized = True
        logger.info("OpenTelemetry initialised → %s", endpoint)
    except Exception:
        logger.warning(
            "OpenTelemetry setup failed — continuing without telemetry",
            exc_info=True,
        )


def _setup_providers(endpoint: str) -> None:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    service_name = os.getenv("OTEL_SERVICE_NAME", "my-backend")
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "0.1.0",
    })

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=30_000,
    )
    metrics.set_meter_provider(
        MeterProvider(resource=resource, metric_readers=[metric_reader])
    )

    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry._logs import set_logger_provider

    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(log_provider)
    logging.getLogger().addHandler(
        LoggingHandler(level=logging.INFO, logger_provider=log_provider)
    )


def _setup_auto_instrumentation() -> None:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=False)


def instrument_app(app: Any) -> None:
    """Instrument a FastAPI application instance. Call after app creation."""
    if not _initialized:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumented with OpenTelemetry")
    except Exception:
        logger.warning("FastAPI OTel instrumentation failed", exc_info=True)


# ── Tracer / Meter accessors ─────────────────────────────────────────

def get_tracer(name: str = "app.backend") -> Any:
    from opentelemetry import trace

    return trace.get_tracer(name)


def get_meter(name: str = "app.backend") -> Any:
    from opentelemetry import metrics

    return metrics.get_meter(name)


# ── Custom agent metrics ──────────────────────────────────────────────

_agent_metrics: dict[str, Any] = {}


def _ensure_agent_metrics() -> None:
    if _agent_metrics:
        return
    meter = get_meter("app.agents")
    _agent_metrics["runs"] = meter.create_counter(
        "agent.runs",
        description="Total agent runs",
        unit="1",
    )
    _agent_metrics["duration"] = meter.create_histogram(
        "agent.run.duration_ms",
        description="Agent run duration",
        unit="ms",
    )
    _agent_metrics["tool_calls"] = meter.create_counter(
        "agent.tool_calls",
        description="Total tool calls",
        unit="1",
    )
    _agent_metrics["errors"] = meter.create_counter(
        "agent.errors",
        description="Agent run errors",
        unit="1",
    )


def record_agent_run(agent_slug: str, duration_ms: float) -> None:
    if not _initialized:
        return
    _ensure_agent_metrics()
    attrs = {"agent.slug": agent_slug}
    _agent_metrics["runs"].add(1, attrs)
    _agent_metrics["duration"].record(duration_ms, attrs)


def record_tool_call(agent_slug: str, tool_name: str) -> None:
    if not _initialized:
        return
    _ensure_agent_metrics()
    _agent_metrics["tool_calls"].add(
        1, {"agent.slug": agent_slug, "tool.name": tool_name}
    )


def record_agent_error(agent_slug: str) -> None:
    if not _initialized:
        return
    _ensure_agent_metrics()
    _agent_metrics["errors"].add(1, {"agent.slug": agent_slug})


# ── LangFuse integration ─────────────────────────────────────────────

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

    LangFuse v4 reads credentials from LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY,
    and LANGFUSE_HOST env vars automatically.  Use ``langfuse_propagate_attributes``
    to attach session/user/agent metadata to the trace.

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
    """Return a ``propagate_attributes`` context manager that sets trace metadata.

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
