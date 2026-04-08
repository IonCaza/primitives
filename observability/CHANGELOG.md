# Changelog

## [2.0.0] - 2026-04-08
### Changed
- **BREAKING**: Removed OTel SDK programmatic setup (`init_telemetry`,
  `instrument_app`, `_setup_providers`, `_setup_auto_instrumentation`,
  `get_tracer`, `get_meter`) from the Python module. OTel SDK is now
  handled via environment-based auto-instrumentation, keeping the Python
  module focused solely on Langfuse integration
  (files: backend/core/telemetry.py)
- **BREAKING**: Removed custom agent metrics (`record_agent_run`,
  `record_tool_call`, `record_agent_error`, `_ensure_agent_metrics`)
  from the Python module — these relied on the removed OTel meter
  (files: backend/core/telemetry.py)
- Upgraded Langfuse from v2 to v3 multi-service architecture
  (files: docker/docker-compose.fragment.yml)
- Langfuse `image` tag changed from `langfuse/langfuse:2` to
  `langfuse/langfuse:3`
  (files: docker/docker-compose.fragment.yml)
- Langfuse now uses YAML anchor (`&langfuse-env` / `<<: *langfuse-env`)
  to share environment between worker and web server
  (files: docker/docker-compose.fragment.yml)

### Added
- New service: `langfuse-clickhouse` — ClickHouse analytics backend
  required by Langfuse v3
  (files: docker/docker-compose.fragment.yml)
- New service: `langfuse-worker` — async background worker required by
  Langfuse v3
  (files: docker/docker-compose.fragment.yml)
- New service: `minio` — S3-compatible object store for Langfuse event
  and media uploads
  (files: docker/docker-compose.fragment.yml)
- ClickHouse environment variables (CLICKHOUSE_MIGRATION_URL,
  CLICKHOUSE_URL, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD,
  CLICKHOUSE_CLUSTER_ENABLED)
  (files: docker/docker-compose.fragment.yml)
- Redis environment variables for Langfuse worker queue
  (REDIS_HOST, REDIS_PORT, REDIS_AUTH)
  (files: docker/docker-compose.fragment.yml)
- S3/MinIO environment variables for event and media storage
  (14 LANGFUSE_S3_* variables)
  (files: docker/docker-compose.fragment.yml)
- Langfuse v3 init variables: LANGFUSE_INIT_ORG_ID,
  LANGFUSE_INIT_PROJECT_ID, LANGFUSE_INIT_USER_EMAIL,
  LANGFUSE_INIT_USER_NAME, LANGFUSE_INIT_USER_PASSWORD
  (files: docker/docker-compose.fragment.yml)
- Pinned image versions for OTel/Grafana stack: otel-collector 0.122.1,
  tempo 2.7.2, prometheus v3.3.1, loki 3.5.0, grafana 11.6.0
  (files: docker/docker-compose.fragment.yml)

### Removed
- OTel SDK Python dependencies no longer required by the telemetry module
  (opentelemetry-api, opentelemetry-sdk, opentelemetry-exporter-*,
  opentelemetry-instrumentation-*)
  (files: backend/core/telemetry.py)

### Migration notes
- **Breaking**: If your app imports `init_telemetry`, `instrument_app`,
  `get_tracer`, `get_meter`, `record_agent_run`, `record_tool_call`, or
  `record_agent_error`, you must remove those calls. OTel SDK setup
  should now be done via environment variables or a separate module.
- **Breaking**: The `langfuse` docker service now requires three additional
  services: `langfuse-clickhouse`, `langfuse-worker`, and `minio`. Your
  app also needs a `redis` service (often already present from cornerstone).
- Langfuse data stored in v2 format will be migrated automatically on
  first startup of the v3 images.
- The OTel/Grafana stack (otel-collector, tempo, prometheus, loki, grafana)
  is now provided as commented-out services. Uncomment to enable.

## [1.0.0] - 2026-03-31
### Added
- Initial extraction from uad36
- OpenTelemetry SDK setup with traces, metrics, and logs pipelines
  (files: backend/core/telemetry.py)
- Auto-instrumentation for SQLAlchemy, Redis, httpx, FastAPI, logging
  (files: backend/core/telemetry.py)
- Custom agent metrics: runs counter, duration histogram, tool calls, errors
  (files: backend/core/telemetry.py)
- LangFuse integration with callback handler and attribute propagation
  (files: backend/core/telemetry.py)
- OTel Collector config routing OTLP to Tempo/Prometheus/Loki
  (files: config/otel-collector.yaml)
- Tempo config for local trace storage
  (files: config/tempo.yaml)
- Prometheus config scraping OTel Collector
  (files: config/prometheus.yaml)
- Loki config for log storage
  (files: config/loki.yaml)
- Grafana datasource provisioning (Tempo, Prometheus, Loki linked)
  (files: config/grafana/provisioning/datasources/datasources.yaml)
- Docker Compose fragment for all observability services
  (files: docker/docker-compose.fragment.yml)

### Migration notes
- No database schema changes
- Requires Docker for infrastructure services
- Backend telemetry module has no dependencies on other app modules
