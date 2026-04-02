"""Job management API: CRUD, trigger, cancel, and SSE log streaming.

Two routers are exported:
  - router: authenticated CRUD + trigger endpoints
  - stream_router: SSE endpoint (auth via ?token= query param because
    EventSource cannot set Authorization headers)
"""
import json
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.db.base import get_db
from app.db.models.job import Job, JobEvent, JobStatus

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
stream_router = APIRouter(prefix="/api/jobs", tags=["jobs"])

STALE_QUEUED = timedelta(minutes=10)
STALE_RUNNING = timedelta(hours=2)


class JobCreate(BaseModel):
    job_type: str
    params: dict = {}


class JobOut(BaseModel):
    id: str
    job_type: str
    status: str
    params: dict | None = None
    result: dict | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


def _serialize(job: Job) -> JobOut:
    return JobOut(
        id=str(job.id),
        job_type=job.job_type,
        status=job.status.value if isinstance(job.status, JobStatus) else job.status,
        params=job.params,
        result=job.result,
        error_message=job.error_message,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        created_at=job.created_at.isoformat(),
    )


@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_job(body: JobCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    blocking = (await db.execute(
        select(Job).where(
            Job.job_type == body.job_type,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )).scalar_one_or_none()

    if blocking:
        is_stale = (
            (blocking.status == JobStatus.QUEUED and blocking.created_at < now - STALE_QUEUED)
            or (blocking.status == JobStatus.RUNNING and (blocking.started_at or blocking.created_at) < now - STALE_RUNNING)
        )
        if is_stale:
            blocking.status = JobStatus.FAILED
            blocking.error_message = "Marked stale by new job request"
            blocking.finished_at = now
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A job of this type is already in progress")

    job = Job(job_type=body.job_type, params=body.params, status=JobStatus.QUEUED)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # --- Dispatch to Celery here ---
    # Import your task and call: your_task.delay(str(job.id))
    # Example:
    #   from app.workers.tasks import example_job
    #   result = example_job.delay(str(job.id))
    #   job.celery_task_id = result.id
    #   await db.commit()

    return _serialize(job)


@router.get("", response_model=list[JobOut])
async def list_jobs(
    job_type: str | None = None,
    job_status: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    q = select(Job).order_by(Job.created_at.desc()).limit(50)
    if job_type:
        q = q.where(Job.job_type == job_type)
    if job_status:
        q = q.where(Job.status == job_status)
    result = await db.execute(q)
    return [_serialize(j) for j in result.scalars().all()]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(status_code=409, detail="Job is not active")
    job.status = JobStatus.CANCELLED
    job.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return _serialize(job)


@router.get("/{job_id}/events")
async def get_job_events(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.timestamp.asc())
    )
    return [
        {
            "id": str(e.id),
            "phase": e.phase,
            "level": e.level,
            "message": e.message,
            "detail": e.detail,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in result.scalars().all()
    ]


@stream_router.get("/{job_id}/logs")
async def stream_job_logs(
    request: Request,
    job_id: str,
    token: str | None = Query(default=None),
):
    """Stream job logs via SSE. Auth via ?token= query param."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    # Validate JWT -- adapt import to your auth module:
    # from app.auth.security import decode_token
    # payload = decode_token(token)
    # if payload is None or payload.get("type") != "access":
    #     raise HTTPException(status_code=401, detail="Invalid token")

    list_key = f"job:logs:{job_id}"
    channel_key = f"job:logs:live:{job_id}"

    async def event_generator():
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            existing = await r.lrange(list_key, 0, -1)
            for entry in existing:
                data = json.loads(entry)
                if data.get("phase") == "__done__":
                    yield {"event": "done", "data": entry}
                    return
                yield {"event": "log", "data": entry}

            pubsub = r.pubsub()
            await pubsub.subscribe(channel_key)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if msg is None:
                        continue
                    data = json.loads(msg["data"])
                    if data.get("phase") == "__done__":
                        yield {"event": "done", "data": msg["data"]}
                        break
                    yield {"event": "log", "data": msg["data"]}
            finally:
                await pubsub.unsubscribe(channel_key)
                await pubsub.aclose()
        finally:
            await r.aclose()

    return EventSourceResponse(event_generator())
