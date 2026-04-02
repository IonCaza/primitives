"""Structured logger for async jobs -- writes to Python logger and Redis.

Dual-write pattern: each log entry is pushed to a Redis list (for replay on
reconnect) and published to a Redis pub/sub channel (for live SSE push).
A __done__ sentinel terminates the stream.
"""
import json
import logging
import time

import redis

from app.config import settings

logger = logging.getLogger(__name__)

LOG_TTL_SECONDS = 3600


class JobLogger:
    def __init__(self, job_id: str):
        self.job_id = str(job_id)
        self.list_key = f"job:logs:{self.job_id}"
        self.channel_key = f"job:logs:live:{self.job_id}"
        self._redis: redis.Redis | None = None
        try:
            self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            logger.debug("JobLogger could not connect to Redis", exc_info=True)

    def _emit(self, phase: str, level: str, message: str):
        entry = json.dumps({
            "ts": time.time(),
            "phase": phase,
            "level": level,
            "message": message,
        })

        py_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(py_level, "[job:%s][%s] %s", self.job_id[:8], phase, message)

        if not self._redis:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.rpush(self.list_key, entry)
            pipe.expire(self.list_key, LOG_TTL_SECONDS)
            pipe.publish(self.channel_key, entry)
            pipe.execute()
        except Exception:
            logger.debug("Failed to publish job log to Redis", exc_info=True)

    def info(self, phase: str, message: str):
        self._emit(phase, "info", message)

    def warning(self, phase: str, message: str):
        self._emit(phase, "warning", message)

    def error(self, phase: str, message: str):
        self._emit(phase, "error", message)

    def complete(self):
        self._emit("complete", "info", "Job completed successfully")
        self._finalize()

    def fail(self, error: str):
        self._emit("error", "error", f"Job failed: {error}")
        self._finalize()

    def cancel(self):
        self._emit("cancelled", "info", "Job cancelled by user")
        self._finalize()

    def _finalize(self):
        sentinel = json.dumps({"ts": time.time(), "phase": "__done__", "level": "info", "message": ""})
        if not self._redis:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.rpush(self.list_key, sentinel)
            pipe.expire(self.list_key, LOG_TTL_SECONDS)
            pipe.publish(self.channel_key, sentinel)
            pipe.execute()
        except Exception:
            pass

    def close(self):
        if self._redis:
            try:
                self._redis.close()
            except Exception:
                pass
