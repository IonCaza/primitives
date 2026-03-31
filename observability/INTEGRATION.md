# Observability -- Integration Guide

> This document is designed for AI agent consumption. Follow each section
> step-by-step to add full observability to a FastAPI/Python backend.

## Prerequisites

- [ ] FastAPI backend application
- [ ] Docker Compose for local development
- [ ] Python 3.11+

## 1. Backend Layer

### 1.1 Dependencies

Add to your `requirements.txt`:

```
opentelemetry-api>=1.20
opentelemetry-sdk>=1.20
opentelemetry-exporter-otlp-proto-grpc>=1.20
opentelemetry-instrumentation-fastapi>=0.41
opentelemetry-instrumentation-sqlalchemy>=0.41
opentelemetry-instrumentation-redis>=0.41
opentelemetry-instrumentation-httpx>=0.41
opentelemetry-instrumentation-logging>=0.41
langfuse>=2.0
```

### 1.2 Module Placement

Copy `backend/core/telemetry.py` into your backend's core module
(e.g., `app/core/telemetry.py`).

**Adaptation notes:**
- Change the default `get_tracer()` and `get_meter()` name arguments
  to match your app name (e.g., `"myapp.backend"`, `"myapp.agents"`)
- The module has no imports from other app modules -- it's fully standalone

### 1.3 Initialization

Call `init_telemetry()` **before** creating your FastAPI app and any
SQLAlchemy engines, so auto-instrumentation can monkey-patch them:

```python
# main.py
from app.core.telemetry import init_telemetry, instrument_app

init_telemetry()  # Must be called FIRST

app = FastAPI()
instrument_app(app)  # Adds FastAPI middleware for request tracing
```

### 1.4 Agent Metrics (Optional)

If using the `agentic-ai-engine` primitive, instrument agent runs:

```python
from app.core.telemetry import record_agent_run, record_tool_call, record_agent_error

# In your agent runner, after each run completes:
record_agent_run(agent_slug, duration_ms)

# In your tool execution wrapper:
record_tool_call(agent_slug, tool_name)

# On agent errors:
record_agent_error(agent_slug)
```

### 1.5 LangFuse Integration (Optional)

For LLM/agent tracing with LangFuse:

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

### 1.6 Environment Variables

Add to your backend service's environment:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=your-app-backend

# LangFuse (optional, for LLM tracing)
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=pk-lf-your-key
LANGFUSE_SECRET_KEY=sk-lf-your-key
```

Telemetry gracefully no-ops when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset.

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
docker-compose. The fragment adds 7 services:

- `otel-collector` -- Receives OTLP, routes to Tempo/Prometheus/Loki
- `tempo` -- Distributed trace storage (port 3200)
- `prometheus` -- Metrics storage + scraping (port 9090)
- `loki` -- Log aggregation (port 3100)
- `grafana` -- Visualization (port 3001)
- `langfuse-db` -- Postgres for LangFuse
- `langfuse` -- LLM/agent tracing UI (port 3002)

**Adaptation notes:**
- Change LangFuse init org/project names and keys
- Adjust host port mappings if they conflict with your app
- Add `depends_on: otel-collector` to your backend service

### 2.3 Data Directories

The services store data in `.docker-data/`:
```
.docker-data/
  tempo/
  prometheus/
  loki/
  grafana/
  langfuse-db/
```

Add `.docker-data/` to your `.gitignore`.

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

- [ ] `docker compose up` starts all 7 observability services
- [ ] Backend logs show "OpenTelemetry initialised" on startup
- [ ] Grafana (http://localhost:3001) shows Tempo, Prometheus, and Loki datasources
- [ ] Prometheus (http://localhost:9090) shows metrics from otel-collector
- [ ] Tempo traces appear in Grafana Explore > Tempo after making API requests
- [ ] LangFuse (http://localhost:3002) shows LLM traces after agent runs (if configured)
