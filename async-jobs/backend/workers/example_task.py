"""Example task demonstrating the canonical async job pattern.

Replace this with your domain-specific tasks. Each task follows the same
structure: a @celery.task sync wrapper that calls asyncio.run() to bridge
into async code.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

from app.db.base import async_session
from app.db.models.job import Job, JobStatus
from app.services.job_logger import JobLogger
from app.workers.base import JobTask, check_cancelled
from app.workers.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="example_job", base=JobTask, bind=True)
def example_job(self, job_id: str) -> dict:
    asyncio.run(_run_example(job_id))
    return {"job_id": job_id}


async def _run_example(job_id: str):
    jlog = JobLogger(job_id)
    try:
        async with async_session() as db:
            job = await db.get(Job, job_id)
            if not job:
                return
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            await db.commit()

            jlog.info("init", "Starting example job")

            for i, phase in enumerate(["fetch", "process", "finalize"]):
                if await check_cancelled(db, job_id):
                    job.status = JobStatus.CANCELLED
                    job.finished_at = datetime.now(timezone.utc)
                    await db.commit()
                    jlog.cancel()
                    return

                jlog.info(phase, f"Running phase {phase} ({i + 1}/3)")
                await asyncio.sleep(2)  # Simulate work
                jlog.info(phase, f"Phase {phase} complete")

            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
            jlog.complete()

    except Exception as exc:
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
