"""AI-powered memory recall: select relevant memories before an agent turn.

Uses a two-tier strategy:
1. If the vector store is available, performs semantic search for fast,
   embedding-based recall (no LLM call needed).
2. Falls back to LLM-based manifest ranking when vector search is
   unavailable or returns nothing.

Selected memories are injected into the system prompt via the modifier.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory.pool import get_store
from app.db.models.agent_memory import AgentMemory

logger = logging.getLogger(__name__)

RECALL_PROMPT = """\
You are selecting which saved memories would help an AI agent handle this request.
You will see a list of memories with their names and short descriptions.

Return up to 5 that are clearly relevant. If none seem useful, return an empty list.
Err on the side of leaving things out -- irrelevant context is worse than missing context.

Do NOT select memories that simply describe database structure (the agent can query
that directly). DO select memories about user preferences, past corrections, business
context, or non-obvious data meanings.

Return your selection as a simple numbered list of memory names, exactly as shown.
If none are relevant, return: NONE
"""

MAX_MEMORIES_TO_RECALL = 5


async def recall_relevant_memories(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    llm,
) -> list[dict]:
    """Select relevant memories for the current request.

    Strategy:
    1. Try vector search (fast, no LLM cost).
    2. If vector search returns nothing or is unavailable, fall back to
       LLM-based manifest ranking.
    3. If <=5 memories exist total, return all without any search.

    Returns a list of dicts with keys: name, type, content, staleness_note.
    """
    all_memories = (
        await db.execute(
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .order_by(AgentMemory.updated_at.desc().nullslast(), AgentMemory.created_at.desc())
        )
    ).scalars().all()

    if not all_memories:
        return []

    if len(all_memories) <= MAX_MEMORIES_TO_RECALL:
        return _format_recalled(all_memories)

    recalled = await _recall_via_vector(db, user_id, query)
    if recalled:
        return recalled

    return await _recall_via_llm(all_memories, query, llm)


async def _recall_via_vector(
    db: AsyncSession, user_id: uuid.UUID, query: str
) -> list[dict]:
    """Use the vector store for semantic recall."""
    store = get_store()
    if store is None:
        return []

    try:
        namespace = ("memories", str(user_id))
        results = await store.asearch(namespace, query=query, limit=MAX_MEMORIES_TO_RECALL)
        if not results:
            return []

        memory_ids = []
        for item in results:
            try:
                memory_ids.append(uuid.UUID(item.key))
            except (ValueError, TypeError):
                continue

        if not memory_ids:
            return []

        memories = (
            await db.execute(
                select(AgentMemory).where(
                    AgentMemory.user_id == user_id,
                    AgentMemory.id.in_(memory_ids),
                )
            )
        ).scalars().all()

        id_order = {mid: i for i, mid in enumerate(memory_ids)}
        memories = sorted(memories, key=lambda m: id_order.get(m.id, 999))

        return _format_recalled(memories)
    except Exception:
        logger.debug("Vector recall failed, will try LLM fallback", exc_info=True)
        return []


async def _recall_via_llm(
    all_memories: list[AgentMemory], query: str, llm
) -> list[dict]:
    """Fall back to LLM-based manifest ranking."""
    manifest = "\n".join(
        f"- [{m.type}] {m.name} ({(m.updated_at or m.created_at).strftime('%Y-%m-%d')}): {m.description}"
        for m in all_memories
    )

    try:
        result = await llm.ainvoke([
            SystemMessage(content=RECALL_PROMPT),
            HumanMessage(content=f"User request: {query}\n\nAvailable memories:\n{manifest}"),
        ])

        selected_names = _parse_selected_names(result.content, {m.name for m in all_memories})
        if not selected_names:
            return []

        recalled = [m for m in all_memories if m.name in selected_names][:MAX_MEMORIES_TO_RECALL]
        return _format_recalled(recalled)
    except Exception:
        logger.debug("LLM recall failed (non-critical)", exc_info=True)
        return []


def _parse_selected_names(text: str, valid_names: set[str]) -> set[str]:
    """Extract memory names from the LLM's selection response."""
    if "NONE" in text.upper():
        return set()

    found = set()
    for name in valid_names:
        if name in text:
            found.add(name)

    if not found:
        for line in text.strip().splitlines():
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line.strip())
            cleaned = cleaned.strip('"').strip("'").strip()
            if cleaned in valid_names:
                found.add(cleaned)

    return found


def _format_recalled(memories: list) -> list[dict]:
    """Convert memories to injection-ready dicts with staleness notes."""
    now = datetime.now(timezone.utc)
    result = []
    for m in memories:
        age_days = (now - (m.updated_at or m.created_at)).days
        staleness = ""
        if age_days > 7:
            staleness = f" (saved {age_days} days ago -- verify before relying on specifics)"
        result.append({
            "name": m.name,
            "type": m.type,
            "content": m.content,
            "staleness_note": staleness,
        })
    return result


def format_recalled_for_prompt(recalled: list[dict]) -> str:
    """Format recalled memories as a prompt section."""
    if not recalled:
        return ""

    lines = ["## Recalled Context\n"]
    for m in recalled:
        lines.append(f"**[{m['type']}] {m['name']}**{m['staleness_note']}")
        lines.append(m["content"])
        lines.append("")
    return "\n".join(lines)
