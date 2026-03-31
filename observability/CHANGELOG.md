# Changelog

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
