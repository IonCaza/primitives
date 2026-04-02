"""Structured memory tools: save, search, update, forget.

Uses the AgentMemory SQLAlchemy model with a 4-type taxonomy
(user, feedback, project, reference) as the structured source of truth.
Dual-writes to the LangGraph AsyncPostgresStore for vector/semantic
search when the store is configured.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool
from sqlalchemy import cast, or_, select, String as SAString
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import current_user_id
from app.agents.memory.pool import get_store
from app.agents.tools.base import ToolDefinition
from app.agents.tools.registry import register_tool_category
from app.db.base import async_session
from app.db.models.agent_memory import AgentMemory

logger = logging.getLogger(__name__)

CATEGORY = "memory"

MEMORY_TYPE_GUIDANCE = """
## Memory Types

### user -- About the person you're working with
Preferences, expertise level, communication style, role.

### feedback -- Corrections and confirmed approaches
Things the user corrected or explicitly approved. Both failures AND successes.

### project -- Living context not found in the data
Deadlines, decisions, team structure, business context.

### reference -- Pointers to external systems
Where to find things outside the immediate workspace.

## What NOT to Save
Do not store anything you can look up on demand: database schema, column types,
SQL syntax, or frequently-changing data values.
"""

DEFINITIONS = [
    ToolDefinition(
        slug="save_memory",
        name="save_memory",
        description="Persist a named, typed memory for future conversations.",
        category=CATEGORY,
    ),
    ToolDefinition(
        slug="search_memories",
        name="search_memories",
        description="Search saved memories by keyword or semantic similarity, optionally filtering by type.",
        category=CATEGORY,
        concurrency_safe=True,
    ),
    ToolDefinition(
        slug="update_memory",
        name="update_memory",
        description="Update the content of an existing memory.",
        category=CATEGORY,
    ),
    ToolDefinition(
        slug="forget_memory",
        name="forget_memory",
        description="Delete a memory that is outdated or incorrect.",
        category=CATEGORY,
    ),
]


async def _mirror_to_store(
    user_id: uuid.UUID, memory_id: uuid.UUID, content: str, metadata: dict
) -> None:
    """Best-effort write to the vector store for semantic search."""
    store = get_store()
    if store is None:
        return
    try:
        namespace = ("memories", str(user_id))
        await store.aput(
            namespace,
            str(memory_id),
            {"text": content, **metadata},
        )
    except Exception:
        logger.debug("Mirror to vector store failed (non-critical)", exc_info=True)


async def _remove_from_store(user_id: uuid.UUID, memory_id: uuid.UUID) -> None:
    """Best-effort delete from the vector store."""
    store = get_store()
    if store is None:
        return
    try:
        namespace = ("memories", str(user_id))
        await store.adelete(namespace, str(memory_id))
    except Exception:
        logger.debug("Delete from vector store failed (non-critical)", exc_info=True)


def _build_memory_tools(db: AsyncSession) -> list:
    """Factory that returns memory tools.

    The ``db`` parameter is unused here because each tool opens its own
    session, but it's required by the registry ToolFactory signature.
    """

    @tool
    async def save_memory(
        name: str, description: str, type: str, content: str
    ) -> str:
        """Persist a piece of knowledge for future conversations.

        Args:
            name: Short identifier (e.g. "revenue-metric-preference").
            description: One line explaining what this memory contains (used to decide relevance later).
            type: One of: user, feedback, project, reference.
            content: The actual memory content.
        """
        valid_types = {"user", "feedback", "project", "reference"}
        if type not in valid_types:
            return f"Invalid type '{type}'. Must be one of: {', '.join(sorted(valid_types))}"

        uid = current_user_id.get()
        if uid is None:
            return "Cannot save memory: no user context available."

        try:
            async with async_session() as db:
                memory = AgentMemory(
                    user_id=uid,
                    name=name,
                    description=description,
                    type=type,
                    content=content,
                )
                db.add(memory)
                await db.commit()
                await db.refresh(memory)

                await _mirror_to_store(uid, memory.id, content, {
                    "name": name, "type": type, "description": description,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                })

                return f"Memory saved: [{type}] {name} (id={str(memory.id)[:8]}...)"
        except Exception:
            logger.exception("Failed to save memory")
            return "Failed to save memory."

    @tool
    async def search_memories(
        query: str, type: str | None = None, limit: int = 10
    ) -> str:
        """Search saved memories by keyword or semantic similarity. Optionally filter by type.

        Args:
            query: Search term (semantic search when vector store is available, keyword fallback).
            type: Optional filter -- one of: user, feedback, project, reference.
            limit: Maximum results (default 10).
        """
        uid = current_user_id.get()
        if uid is None:
            return "Cannot search memories: no user context available."

        try:
            vector_ids = await _vector_search(uid, query, limit)

            async with async_session() as db:
                if vector_ids:
                    stmt = select(AgentMemory).where(
                        AgentMemory.user_id == uid,
                        AgentMemory.id.in_(vector_ids),
                    )
                    if type:
                        stmt = stmt.where(AgentMemory.type == type)
                    results = (await db.execute(stmt)).scalars().all()

                    id_order = {vid: i for i, vid in enumerate(vector_ids)}
                    results = sorted(results, key=lambda m: id_order.get(m.id, 999))
                else:
                    stmt = select(AgentMemory).where(AgentMemory.user_id == uid)
                    if type:
                        stmt = stmt.where(AgentMemory.type == type)
                    pattern = f"%{query}%"
                    stmt = stmt.where(
                        or_(
                            AgentMemory.name.ilike(pattern),
                            AgentMemory.description.ilike(pattern),
                            AgentMemory.content.ilike(pattern),
                        )
                    )
                    stmt = stmt.order_by(
                        AgentMemory.updated_at.desc().nullslast(),
                        AgentMemory.created_at.desc(),
                    )
                    stmt = stmt.limit(limit)
                    results = (await db.execute(stmt)).scalars().all()

                if not results:
                    return "No matching memories found."

                lines = []
                for m in results:
                    age = (datetime.now(timezone.utc) - (m.updated_at or m.created_at)).days
                    stale = f" (saved {age}d ago -- verify before relying on specifics)" if age > 1 else ""
                    lines.append(
                        f"- [{m.type}] **{m.name}** (id={str(m.id)[:8]}...): {m.description}\n  {m.content}{stale}"
                    )
                return f"Found {len(results)} memories:\n" + "\n".join(lines)
        except Exception:
            logger.exception("Failed to search memories")
            return "Failed to search memories."

    @tool
    async def update_memory(memory_id: str, content: str) -> str:
        """Update the content of an existing memory.

        Args:
            memory_id: The full or partial UUID of the memory to update.
            content: The new content to replace the existing content.
        """
        uid = current_user_id.get()
        if uid is None:
            return "Cannot update memory: no user context available."

        try:
            async with async_session() as db:
                memory = await _find_memory(db, uid, memory_id)
                if memory is None:
                    return f"Memory '{memory_id}' not found."
                memory.content = content
                await db.commit()

                await _mirror_to_store(uid, memory.id, content, {
                    "name": memory.name, "type": memory.type,
                    "description": memory.description,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                })

                return f"Memory updated: [{memory.type}] {memory.name}"
        except Exception:
            logger.exception("Failed to update memory")
            return "Failed to update memory."

    @tool
    async def forget_memory(memory_id: str) -> str:
        """Delete a memory that is outdated or incorrect.

        Args:
            memory_id: The full or partial UUID of the memory to delete.
        """
        uid = current_user_id.get()
        if uid is None:
            return "Cannot delete memory: no user context available."

        try:
            async with async_session() as db:
                memory = await _find_memory(db, uid, memory_id)
                if memory is None:
                    return f"Memory '{memory_id}' not found."
                name = memory.name
                mid = memory.id
                await db.delete(memory)
                await db.commit()

                await _remove_from_store(uid, mid)

                return f"Memory deleted: {name}"
        except Exception:
            logger.exception("Failed to delete memory")
            return "Failed to delete memory."

    return [save_memory, search_memories, update_memory, forget_memory]


async def _vector_search(
    user_id: uuid.UUID, query: str, limit: int
) -> list[uuid.UUID]:
    """Attempt semantic search via the vector store. Returns matching memory UUIDs."""
    store = get_store()
    if store is None:
        return []
    try:
        namespace = ("memories", str(user_id))
        results = await store.asearch(namespace, query=query, limit=limit)
        return [uuid.UUID(item.key) for item in results if item.key]
    except Exception:
        logger.debug("Vector search failed, falling back to keyword", exc_info=True)
        return []


async def _find_memory(
    db: AsyncSession, user_id: uuid.UUID, memory_id: str
) -> AgentMemory | None:
    """Find a memory by full UUID or prefix match."""
    try:
        full_id = uuid.UUID(memory_id)
        return (
            await db.execute(
                select(AgentMemory).where(
                    AgentMemory.id == full_id, AgentMemory.user_id == user_id
                )
            )
        ).scalar_one_or_none()
    except ValueError:
        pass

    results = (
        await db.execute(
            select(AgentMemory).where(
                AgentMemory.user_id == user_id,
                cast(AgentMemory.id, SAString).like(f"{memory_id}%"),
            )
        )
    ).scalars().all()
    return results[0] if len(results) == 1 else None


def build_memory_tools(user_id: uuid.UUID) -> list:
    """Legacy entry point -- returns the new typed memory tools.

    The user_id parameter is kept for API compatibility but the tools
    now read from ``current_user_id`` ContextVar internally.
    """
    return _build_memory_tools(None)


register_tool_category(CATEGORY, DEFINITIONS, _build_memory_tools, session_safe=True)
