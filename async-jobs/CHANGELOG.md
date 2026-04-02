# async-jobs Changelog

## 1.0.0 — 2026-03-31

Initial extraction from **contributr** and **updatr**.

### Source commits
- contributr: `fab41bb728373d1087389b2a785a476b36730368`
- updatr: `7f64e9ca69acbf40c6b2c855e37446ec60b877c4`

### Files
- `schema/job.py` — Job + JobEvent models, JobStatus enum
- `backend/workers/celery_app.py` — Celery app configuration
- `backend/workers/base.py` — JobTask base class, async bridge, orphan cleanup, cancellation
- `backend/workers/example_task.py` — Example task showing canonical pattern
- `backend/services/job_logger.py` — Structured dual-write logger (Redis list + pub/sub)
- `backend/api/jobs.py` — CRUD, trigger, cancel, SSE streaming endpoints
- `backend/requirements.txt` — Python dependencies
- `frontend/components/job-log-viewer.tsx` — Terminal-style SSE log viewer
- `frontend/components/job-status-badge.tsx` — Status badge with icons
- `frontend/hooks/use-jobs.ts` — React Query hooks with conditional polling
- `config/docker-compose.fragment.yml` — Celery worker + beat services

### Canonicalization decisions
- **Dual Redis write** (contributr pattern): list for replay, pub/sub for live push
- **sse-starlette** (contributr): cleaner SSE handling vs raw StreamingResponse
- **Unified Job model**: single table with `job_type` field, not per-type models
- **JobStatus enum**: superset of both apps (queued/running/completed/failed/cancelled)
- **React Query hooks**: conditional 3s polling when jobs active (contributr pattern)
- **Generic phase colors**: fetch/process/validate/transform/persist/finalize
- **Stripped domain logic**: no git/ansible/host routing/wave orchestration
