"""LangGraph memory infrastructure: psycopg pool, checkpointer, and store.

LangGraph requires psycopg (not asyncpg) for its checkpointer and store.
We maintain a dedicated psycopg AsyncConnectionPool separate from the
SQLAlchemy asyncpg engine used by the rest of the application.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

from app.config import settings

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_store: AsyncPostgresStore | None = None


def _derive_psycopg_dsn() -> str:
    """Convert the SQLAlchemy database_url to a raw psycopg DSN."""
    url = settings.database_url
    url = re.sub(r"^postgresql\+\w+://", "postgresql://", url)
    return url


async def init_memory_pool(
    *,
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    embed_dims: int = 1536,
) -> None:
    """Open the psycopg pool, initialise checkpointer and store tables."""
    global _pool, _checkpointer, _store

    dsn = _derive_psycopg_dsn()
    _pool = AsyncConnectionPool(
        conninfo=dsn,
        min_size=2,
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
    await _pool.open()

    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()
    logger.info("LangGraph AsyncPostgresSaver ready")

    if embed_fn is not None:
        _store = AsyncPostgresStore(
            _pool,
            index={
                "dims": embed_dims,
                "embed": embed_fn,
                "fields": ["text"],
            },
        )
        await _store.setup()
        logger.info("LangGraph AsyncPostgresStore ready (dims=%d)", embed_dims)
    else:
        logger.info("No embedding provider configured — AsyncPostgresStore skipped")


async def close_memory_pool() -> None:
    global _pool, _checkpointer, _store
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None
    _store = None


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("Memory pool not initialised — call init_memory_pool first")
    return _checkpointer


def get_store() -> AsyncPostgresStore | None:
    return _store
