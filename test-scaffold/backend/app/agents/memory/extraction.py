"""Tier 3: LangMem background memory extraction.

After each agent turn, extracts facts, preferences, and patterns from
the conversation and stores them in the long-term PostgresStore.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.agents.memory.pool import get_store
from app.db.base import async_session
from app.db.models.ai_settings import AiSettings, SINGLETON_ID

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

_manager = None
_manager_model: str | None = None


def invalidate_extraction_cache() -> None:
    """Force the manager to be rebuilt on next call (e.g. after settings change)."""
    global _manager, _manager_model
    _manager = None
    _manager_model = None


async def _resolve_extraction_model() -> tuple[str | None, dict]:
    """Read AiSettings to determine the extraction model string and langmem flags."""
    try:
        async with async_session() as db:
            row = (await db.execute(
                select(AiSettings).where(AiSettings.id == SINGLETON_ID)
            )).scalar_one_or_none()

            if not row or not row.extraction_enabled:
                return None, {}

            flags = {
                "enable_inserts": row.extraction_enable_inserts,
                "enable_updates": row.extraction_enable_updates,
                "enable_deletes": row.extraction_enable_deletes,
            }

            if not row.extraction_provider_id:
                return None, flags

            from app.db.models.llm_provider import LlmProvider
            provider = (await db.execute(
                select(LlmProvider).where(LlmProvider.id == row.extraction_provider_id)
            )).scalar_one_or_none()

            if not provider:
                return None, flags

            return provider.model, flags
    except Exception:
        logger.debug("Failed to resolve extraction model from settings", exc_info=True)
        return None, {}


async def _get_memory_manager():
    """Lazy-init the memory store manager (requires langmem + store + configured provider)."""
    global _manager, _manager_model

    store = get_store()
    if store is None:
        return None

    model, flags = await _resolve_extraction_model()
    if not model:
        return None

    if _manager is not None and _manager_model == model:
        return _manager

    try:
        from langmem import create_memory_store_manager

        _manager = create_memory_store_manager(
            model,
            namespace=("memories", "{user_id}"),
            **flags,
        )
        _manager_model = model
        logger.info("LangMem memory store manager initialised with model=%s", model)
        return _manager
    except Exception:
        logger.debug("LangMem not available or failed to initialise", exc_info=True)
        return None


async def extract_memories(
    user_id: uuid.UUID,
    messages: list[dict],
) -> None:
    """Extract memories from a turn's messages in the background.

    Args:
        user_id: Scope extraction to this user's namespace.
        messages: List of {"role": ..., "content": ...} dicts from the turn.
    """
    manager = await _get_memory_manager()
    if manager is None:
        return

    try:
        formatted = []
        for msg in messages:
            formatted.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        await manager.ainvoke(
            {"messages": formatted},
            config={"configurable": {"user_id": str(user_id)}},
        )
        logger.debug("LangMem extraction completed for user %s", user_id)
    except Exception:
        logger.debug("LangMem extraction failed (non-critical)", exc_info=True)
