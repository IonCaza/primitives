# Observability -- Integration Guide

> This document is designed for AI agent consumption. Follow each section
> step-by-step to add full observability to a FastAPI/Python backend.

## Prerequisites

- [ ] FastAPI backend application
- [ ] Docker Compose for local development
- [ ] Python 3.11+
- [ ] A Redis service (typically provided by the cornerstone primitive)

## 1. Backend Layer

### 1.1 Dependencies

Add to your `requirements.txt` (or `pyproject.toml`):

```
langfuse>=2.0
```

**Note:** OTel SDK packages (`opentelemetry-api`, `opentelemetry-sdk`,
`opentelemetry-instrumentation-*`) are no longer required by the telemetry
module. If you want OTel auto-instrumentation, install those packages
separately and configure via environment variables.

### 1.2 Module Placement

Copy `backend/core/telemetry.py` into your backend's core module
(e.g., `app/core/telemetry.py`).

**Adaptation notes:**
- The module has no imports from other app modules -- it's fully standalone
- It only provides Langfuse integration; OTel SDK setup is handled via
  environment variables (see Section 1.5)

### 1.3 Langfuse Integration

For LLM/agent tracing with Langfuse:

```python
from app.core.telemetry import create_langfuse_handler, langfuse_propagate_attributes

# In your agent runner:
handler = create_langfuse_handler()
callbacks = [handler] if handler else []

# Wrap agent invocation with trace metadata:
with langfuse_propagate_attributes(
    session_id=str(session_id),
    user_id=str(user_id),
    agent_slug=agent_slug,
):
    result = await agent.ainvoke(input, config={"callbacks": callbacks})
```

### 1.4 Environment Variables

Add to your backend service's environment:

```bash
# Langfuse (required for LLM tracing)
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=pk-lf-your-key       # ADAPT: match docker-compose init keys
LANGFUSE_SECRET_KEY=sk-lf-your-key       # ADAPT: match docker-compose init keys

# OTel (optional, only if enabling the traces/metrics/logs stack)
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=your-app-backend
```

The Langfuse module gracefully no-ops when `LANGFUSE_HOST` is unset.

### 1.5 OTel Auto-Instrumentation (Optional)

If you enable the OTel/Grafana stack (Section 2.2), configure OTel SDK
via environment variables on your backend service rather than programmatic
setup. This allows the OTel agent to instrument SQLAlchemy, Redis, httpx,
FastAPI, etc. without code changes:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=your-app-backend
OTEL_TRACES_EXPORTER=otlp
OTEL_METRICS_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
```

Alternatively, install `opentelemetry-distro` and run your app with
`opentelemetry-instrument python -m uvicorn ...` for zero-code
instrumentation.

## 2. Infrastructure

### 2.1 Config Files

Copy the config files into your project's `observability/` directory:

```
observability/
  otel-collector.yaml    # from config/otel-collector.yaml
  prometheus.yaml        # from config/prometheus.yaml
  tempo.yaml             # from config/tempo.yaml
  loki.yaml              # from config/loki.yaml
  grafana/
    provisioning/
      datasources/
        datasources.yaml # from config/grafana/provisioning/datasources/datasources.yaml
```

**Adaptation notes for otel-collector.yaml:**
- Change `service.namespace` resource attribute from `myapp` to your app name
- Change `prometheus.namespace` from `myapp` to your app name

### 2.2 Docker Compose

Merge `docker/docker-compose.fragment.yml` into your project's
docker-compose. The fragment provides two groups of services:

**Langfuse v3 stack (always active):**
- `langfuse-db` -- Postgres for Langfuse metadata
- `langfuse-clickhouse` -- ClickHouse analytics backend
- `langfuse-worker` -- Async background worker for trace processing
- `langfuse` -- Web UI + API (port 3002)
- `minio` -- S3-compatible blob store for event/media uploads (ports 9000, 9001)

**OTel/Grafana stack (commented out, uncomment to enable):**
- `otel-collector` -- Receives OTLP, routes to Tempo/Prometheus/Loki
- `tempo` -- Distributed trace storage (port 3200)
- `prometheus` -- Metrics storage + scraping (port 9090)
- `loki` -- Log aggregation (port 3100)
- `grafana` -- Visualization (port 3001)

**Adaptation notes:**
- Change Langfuse init org/project names, keys, and admin credentials
- The `langfuse-worker` expects a `redis` service -- if your app already
  has one (e.g., from cornerstone), it will be shared. If not, you need
  to add a Redis service and add `redis` to `langfuse-worker.depends_on`.
- Adjust host port mappings if they conflict with your app
- Add `depends_on: langfuse-db` to your backend if it needs to wait for
  Langfuse to be ready
- For production: use env var substitution for secrets (see the prod
  docker-compose in uad36 for reference)

**YAML anchor pattern:** The fragment uses `&langfuse-env` on
`langfuse-worker` and `<<: *langfuse-env` on `langfuse` to share the
~30 environment variables. Keep this pattern when adapting.

### 2.3 Data Directories

The services store data in `.docker-data/`:
```
.docker-data/
  langfuse-db/
  langfuse-clickhouse/
  langfuse-clickhouse-logs/
  minio/
  tempo/          # if OTel stack enabled
  prometheus/     # if OTel stack enabled
  loki/           # if OTel stack enabled
  grafana/        # if OTel stack enabled
```

Add `.docker-data/` to your `.gitignore`.

For production, use named Docker volumes instead of bind mounts.

## 3. Grafana Dashboards (Extension Point)

The base installation provisions datasources only. To add dashboards:

1. Create a provisioning config at
   `observability/grafana/provisioning/dashboards/dashboards.yaml`:
   ```yaml
   apiVersion: 1
   providers:
     - name: default
       folder: ""
       type: file
       options:
         path: /etc/grafana/provisioning/dashboards
   ```

2. Add JSON dashboard files in the same directory.

3. Mount the directory in docker-compose (already done by the fragment).

## 4. Verification

- [ ] `docker compose up` starts Langfuse stack (langfuse-db, langfuse-clickhouse, langfuse-worker, langfuse, minio)
- [ ] Backend logs show "LangFuse enabled" on startup (when env vars are set)
- [ ] Langfuse UI (http://localhost:3002) is accessible and shows the configured project
- [ ] After an agent run, traces appear in Langfuse with session/user/agent metadata
- [ ] (If OTel stack enabled) Grafana (http://localhost:3001) shows Tempo, Prometheus, Loki datasources
- [ ] (If OTel stack enabled) Tempo traces appear after making API requests
