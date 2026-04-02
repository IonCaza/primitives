"""Base task class and async-in-sync bridge for Celery tasks.

All Celery tasks run synchronously. Domain tasks call asyncio.run() to bridge
into async code that uses the async SQLAlchemy session.
"""
import asyncio
import logging

from celery.signals import worker_ready
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


class JobTask(celery.Task):
    """Base task that marks the Job row as FAILED if the worker process crashes."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = args[0] if args else kwargs.get("job_id")
        if job_id:
            try:
                asyncio.run(_mark_failed(str(job_id), str(exc)))
            except Exception:
                logger.exception("on_failure hook could not mark job %s as failed", job_id)


async def _mark_failed(job_id: str, error: str):
    from app.db.models.job import Job, JobStatus

    async with async_session() as db:
        await db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status=JobStatus.FAILED, error_message=error[:2000])
        )
        await db.commit()


async def cleanup_orphaned_jobs():
    """Reset any jobs stuck in RUNNING/QUEUED from a previous worker crash."""
    from app.db.models.job import Job, JobStatus

    async with async_session() as db:
        await db.execute(
            update(Job)
            .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            .values(status=JobStatus.FAILED, error_message="Worker restarted — job orphaned")
        )
        await db.commit()
        logger.info("Cleaned up orphaned jobs")


@worker_ready.connect
def _on_worker_ready(sender, **kwargs):
    try:
        asyncio.run(cleanup_orphaned_jobs())
    except Exception:
        logger.exception("Failed to clean up orphaned jobs on startup")


async def check_cancelled(db: AsyncSession, job_id) -> bool:
    """Cooperative cancellation check. Call periodically inside long-running tasks."""
    from app.db.models.job import Job, JobStatus

    result = await db.execute(select(Job.status).where(Job.id == str(job_id)))
    row = result.scalar_one_or_none()
    return row == JobStatus.CANCELLED
