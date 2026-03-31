"""Lightweight in-memory cache for AiSettings values used per-request.

Avoids hitting the DB on every agent turn for threshold/ratio values.
The cache refreshes at most once every REFRESH_INTERVAL_SECONDS.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.db.base import async_session
from app.db.models.ai_settings import AiSettings, SINGLETON_ID

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 30


@dataclass(frozen=True)
class MemorySettings:
    memory_enabled: bool = True
    extraction_enabled: bool = True
    cleanup_threshold_ratio: float = 0.6
    summary_token_ratio: float = 0.04


_cached: MemorySettings | None = None
_last_refresh: float = 0.0
_lock = asyncio.Lock()


async def get_memory_settings() -> MemorySettings:
    """Return cached AiSettings values, refreshing if stale."""
    global _cached, _last_refresh

    now = time.monotonic()
    if _cached is not None and (now - _last_refresh) < REFRESH_INTERVAL_SECONDS:
        return _cached

    async with _lock:
        if _cached is not None and (now - _last_refresh) < REFRESH_INTERVAL_SECONDS:
            return _cached
        try:
            async with async_session() as db:
                row = (await db.execute(
                    select(AiSettings).where(AiSettings.id == SINGLETON_ID)
                )).scalar_one_or_none()
                if row:
                    _cached = MemorySettings(
                        memory_enabled=row.memory_enabled,
                        extraction_enabled=row.extraction_enabled,
                        cleanup_threshold_ratio=row.cleanup_threshold_ratio,
                        summary_token_ratio=row.summary_token_ratio,
                    )
                else:
                    _cached = MemorySettings()
                _last_refresh = time.monotonic()
        except Exception:
            logger.debug("Failed to refresh memory settings cache", exc_info=True)
            if _cached is None:
                _cached = MemorySettings()

    return _cached


def invalidate_cache() -> None:
    """Force the next call to re-read from DB."""
    global _cached, _last_refresh
    _cached = None
    _last_refresh = 0.0
