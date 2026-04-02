"""Ambient context for the current agent invocation.

ContextVars propagate automatically into child asyncio tasks, so tools
executed in parallel via ``asyncio.gather`` and child agents spawned via
delegation all inherit the values set by the top-level runner.

Usage in tools::

    from app.agents.context import current_user_id, current_session_id
    uid = current_user_id.get()  # uuid.UUID | None
"""

from __future__ import annotations

import contextvars
import uuid

current_user_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "current_user_id", default=None,
)

current_session_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "current_session_id", default=None,
)
