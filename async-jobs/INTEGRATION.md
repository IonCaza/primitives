# async-jobs Integration Guide

This guide walks an AI agent (or human developer) through adding the async-jobs
primitive to an application built on the **cornerstone** primitive. The result is
a fully functional Celery-based job execution pipeline with real-time SSE log
streaming.

**Prerequisites**: An application with the cornerstone primitive applied (FastAPI
backend, Next.js frontend, PostgreSQL, Redis).

---

## 1. Backend Dependencies

Add to `backend/requirements.txt`:

```
celery[redis]>=5.4,<6
redis>=5.0,<6
sse-starlette>=2.0,<3
```

Run `pip install -r requirements.txt` to install.

---

## 2. Database Models

### 2.1 Copy the Job model

Copy `schema/job.py` to your app's models directory:

```
cp schema/job.py → backend/app/db/models/job.py
```

**Adapt**:
- Update the `Base` import to match your app:
  `from app.db.base import Base`
- Add both `Job` and `JobEvent` to your models `__init__.py` so Alembic
  discovers them:
  ```python
  from app.db.models.job import Job, JobEvent, JobStatus
  ```

### 2.2 Create migration

```bash
cd backend
alembic revision --autogenerate -m "add job and job_event tables"
alembic upgrade head
```

---

## 3. Backend Modules

### 3.1 Celery App

Copy `backend/workers/celery_app.py` to:

```
backend/app/workers/celery_app.py
```

**Adapt**:
- Change the Celery app name from `"myapp"` to your app name.
- Update `settings.redis_url` import path if your config uses a different
  attribute name (e.g., `settings.REDIS_URL`).
- Update the `include` list to point to your task modules:
  ```python
  include=["app.workers.tasks"],
  ```
- Add a `beat_schedule` dict if you need periodic tasks:
  ```python
  beat_schedule={
      "my-periodic-job": {
          "task": "my_task_name",
          "schedule": 60.0,  # or crontab(hour=2, minute=0)
      },
  },
  ```

### 3.2 Base Task & Worker Hooks

Copy `backend/workers/base.py` to:

```
backend/app/workers/base.py
```

**Adapt**:
- Update `from app.db.base import async_session` to match your session maker.
- Update `from app.workers.celery_app import celery` to match your celery app path.
- Update `from app.db.models.job import Job, JobStatus` to match your model path.

### 3.3 Job Logger

Copy `backend/services/job_logger.py` to:

```
backend/app/services/job_logger.py
```

**Adapt**:
- Update `from app.config import settings` if your config path differs.
- Ensure `settings.redis_url` resolves to your Redis connection string.

### 3.4 Example Task

Copy `backend/workers/example_task.py` to:

```
backend/app/workers/example_task.py
```

This is a reference implementation. **Replace** the example phases with your
domain logic:

```python
# In contributr, this becomes sync_repository:
#   phases: clone, commits, branches, prs, stats
#
# In updatr, this becomes patch_hosts:
#   phases: inventory, playbook, verify, report
```

**Pattern to follow for every task**:

```python
@celery.task(name="your_task", base=JobTask, bind=True)
def your_task(self, job_id: str, extra_arg: str) -> dict:
    asyncio.run(_run_your_task(job_id, extra_arg))
    return {"job_id": job_id}

async def _run_your_task(job_id: str, extra_arg: str):
    jlog = JobLogger(job_id)
    try:
        async with async_session() as db:
            job = await db.get(Job, job_id)
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            await db.commit()

            jlog.info("phase_name", "Description of what's happening")

            # Check for cancellation periodically in long loops:
            if await check_cancelled(db, job_id):
                job.status = JobStatus.CANCELLED
                job.finished_at = datetime.now(timezone.utc)
                await db.commit()
                jlog.cancel()
                return

            # ... your domain work ...

            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
            jlog.complete()
    except Exception as exc:
        # Mark failed in DB and log
        async with async_session() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.finished_at = datetime.now(timezone.utc)
                job.error_message = str(exc)[:2000]
                await db.commit()
        jlog.fail(str(exc))
        raise
    finally:
        jlog.close()
```

### 3.5 Job API Routes

Copy `backend/api/jobs.py` to:

```
backend/app/api/jobs.py
```

**Adapt**:
- Update imports for `get_db`, `Job`, `JobEvent`, `JobStatus`, `settings`.
- Add your auth dependency to the `router`:
  ```python
  from app.auth.dependencies import get_current_user
  router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(get_current_user)])
  ```
- **Uncomment** the JWT validation block in `stream_job_logs` and adapt the
  `decode_token` import to your auth module.
- **Wire up task dispatch** in `create_job`:
  ```python
  from app.workers.tasks import your_task
  result = your_task.delay(str(job.id))
  job.celery_task_id = result.id
  await db.commit()
  ```

### 3.6 Register Routes

In `backend/app/main.py`, add:

```python
from app.api.jobs import router as jobs_router, stream_router as jobs_stream_router

app.include_router(jobs_router)
app.include_router(jobs_stream_router)
```

The `stream_router` is separate because SSE auth uses `?token=` query params
instead of the `Authorization` header.

---

## 4. Frontend

### 4.1 Job Log Viewer Component

Copy `frontend/components/job-log-viewer.tsx` to:

```
frontend/src/components/job-log-viewer.tsx
```

**Adapt**:
- Update `localStorage.getItem("access_token")` to match your token storage
  key (the authentication primitive uses `"access_token"`).
- Extend `PHASE_COLORS` for your domain phases:
  ```tsx
  <JobLogViewer
    jobId={job.id}
    phaseColors={{
      clone: "bg-blue-500",
      commits: "bg-violet-500",
      // ... your domain phases
    }}
  />
  ```

### 4.2 Job Status Badge

Copy `frontend/components/job-status-badge.tsx` to:

```
frontend/src/components/job-status-badge.tsx
```

No adaptation needed. Uses shadcn Badge + lucide icons.

### 4.3 React Query Hooks

Copy `frontend/hooks/use-jobs.ts` to:

```
frontend/src/hooks/use-jobs.ts
```

**Adapt**:
- Update `import { request } from "@/lib/api-client"` to match your API
  client's import path and function name.

### 4.4 Usage Example

A minimal job list page:

```tsx
"use client";

import { useJobs, useCreateJob, useCancelJob } from "@/hooks/use-jobs";
import { JobLogViewer } from "@/components/job-log-viewer";
import { JobStatusBadge } from "@/components/job-status-badge";
import { Button } from "@/components/ui/button";

export default function JobsPage() {
  const { data: jobs } = useJobs();
  const createJob = useCreateJob();
  const cancelJob = useCancelJob();

  return (
    <div className="space-y-4">
      <Button
        onClick={() => createJob.mutate({ job_type: "example", params: {} })}
        disabled={createJob.isPending}
      >
        Run Job
      </Button>

      {jobs?.map((job) => (
        <div key={job.id} className="space-y-2 border rounded-lg p-4">
          <div className="flex items-center justify-between">
            <JobStatusBadge status={job.status} />
            {(job.status === "queued" || job.status === "running") && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => cancelJob.mutate(job.id)}
              >
                Cancel
              </Button>
            )}
          </div>
          {(job.status === "queued" || job.status === "running") && (
            <JobLogViewer jobId={job.id} compact />
          )}
        </div>
      ))}
    </div>
  );
}
```

---

## 5. Infrastructure

### 5.1 Docker Compose

Merge the services from `config/docker-compose.fragment.yml` into your
project's `docker-compose.yml`:

```yaml
services:
  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A app.workers.celery_app worker --loglevel=info
    env_file: .env
    depends_on:
      backend:
        condition: service_started
      redis:
        condition: service_healthy
    restart: unless-stopped

  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A app.workers.celery_app beat --loglevel=info
    env_file: .env
    depends_on:
      backend:
        condition: service_started
      redis:
        condition: service_healthy
    restart: unless-stopped
```

For development, you may also add hot-reload overrides in
`docker-compose.dev.yml`:

```yaml
services:
  celery-worker:
    command: celery -A app.workers.celery_app worker --loglevel=debug
    volumes:
      - ./backend:/app
```

### 5.2 Environment Variables

No additional environment variables are required beyond what cornerstone
provides. The Celery app uses the same `REDIS_URL` / `redis_url` already
configured for your app.

---

## 6. Real-World Examples

### Example: Git Repository Sync (contributr)

```python
@celery.task(name="sync_repository", base=JobTask)
def sync_repository(job_id: str, repo_id: str) -> dict:
    asyncio.run(_run_sync(job_id, repo_id))
    return {"job_id": job_id, "repo_id": repo_id}

async def _run_sync(job_id: str, repo_id: str):
    jlog = JobLogger(job_id)
    async with async_session() as db:
        job = await db.get(Job, job_id)
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        jlog.info("clone", "Cloning repository...")
        # ... git clone logic ...

        jlog.info("commits", "Extracting commit history...")
        # ... parse git log ...
        # Cancellation check between phases:
        if await check_cancelled(db, job_id): ...

        jlog.info("prs", "Fetching pull requests from platform API...")
        # ... GitHub/GitLab API calls ...

        jlog.info("stats", "Computing contributor statistics...")
        # ... aggregate metrics ...

        job.status = JobStatus.COMPLETED
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        jlog.complete()
```

### Example: OS Patching (updatr)

```python
@celery.task(name="patch_hosts", base=JobTask, max_retries=1)
def patch_hosts(job_id: str, host_ids: list[str], extra_vars: dict) -> dict:
    # Celery tasks are sync -- bridge to async or use sync DB sessions
    _update_job_status(job_id, "running")

    hosts, creds = _load_hosts_and_creds(host_ids)
    for group in group_by_os(hosts):
        playbook = select_playbook(group.os_family)
        run_playbook(
            playbook, inventory, extra_vars,
            event_callback=_make_event_handler(job_id),
        )

    _update_job_status(job_id, "completed")
    return {"job_id": job_id}

def _make_event_handler(job_id: str):
    def handler(event: dict):
        log_entry = {
            "type": "event",
            "host": event.get("host", ""),
            "task": event.get("task", ""),
            "status": event.get("status", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        _redis.publish(f"job:{job_id}", json.dumps(log_entry))
        _save_event(job_id, ...)
    return handler
```

---

## 7. Architecture Overview

```
                  ┌─────────────┐
                  │  Frontend   │
                  │  (Next.js)  │
                  └──────┬──────┘
                         │
              POST /api/jobs  ←──── create job
              GET  /api/jobs/{id}/logs  ←── SSE stream
                         │
                  ┌──────┴──────┐
                  │   FastAPI   │
                  │   Backend   │
                  └──────┬──────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
        ┌─────┴────┐  ┌─┴──┐  ┌───┴────┐
        │ PostgreSQL│  │Redis│  │ Celery │
        │   (jobs   │  │    │  │ Worker │
        │   table)  │  │    │  └───┬────┘
        └──────────┘  │    │      │
                      │    │   JobLogger
                      │    │      │
                      │    │  rpush (list) + publish (channel)
                      │    │      │
                      └────┘      │
                SSE endpoint ─────┘
                 lrange (replay) + subscribe (live)
```

### Key patterns

| Pattern | Description |
|---------|-------------|
| **Async-in-sync bridge** | `@celery.task` sync wrapper calls `asyncio.run()` |
| **JobTask base** | `on_failure` marks DB row as FAILED on worker crash |
| **Orphan cleanup** | `worker_ready` signal resets stuck RUNNING/QUEUED jobs |
| **Dual Redis write** | List for replay on reconnect + pub/sub for live push |
| **`__done__` sentinel** | Signals stream completion to SSE clients |
| **Stale detection** | New job request auto-fails stale blocking jobs |
| **Cooperative cancel** | Task checks DB for CANCELLED status between phases |
| **Conditional polling** | React Query polls every 3s only when jobs are active |
| **SSE query-param auth** | `?token=JWT` because EventSource can't set headers |
