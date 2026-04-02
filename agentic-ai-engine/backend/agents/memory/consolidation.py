"""Memory consolidation ("dreaming"): periodic maintenance of long-term memories.

Reviews existing AgentMemory entries against recent session summaries and
decides what to keep, update, merge, or delete. Prevents memory rot by
removing stale entries and consolidating redundant ones.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session
from app.db.models.agent_memory import AgentMemory
from app.db.models.chat import ChatSession
from app.db.models.user import User

logger = logging.getLogger(__name__)

CONSOLIDATION_COOLDOWN_HOURS = 24
MIN_SESSIONS_BEFORE_CONSOLIDATION = 5

CONSOLIDATION_PROMPT = """\
You are performing memory maintenance for a user's long-term memory store.
Review the memories below alongside recent session summaries, then decide
what to keep, update, merge, or remove.

Guidelines:
- Merge memories about the same topic into one comprehensive entry
- Update memories with stale information (convert relative dates to absolute,
  correct facts contradicted by recent sessions)
- Remove memories about temporary situations that have resolved
- Keep the total count manageable -- combine related items rather than accumulating
- Preserve high-value memories: user preferences, confirmed workflows, project context

For each memory, output one action:
- {{"action": "keep", "id": "<uuid>"}}
- {{"action": "update", "id": "<uuid>", "content": "new content", "description": "new desc"}}
- {{"action": "merge", "id": "<uuid>", "merge_into": "<target_uuid>", "merged_content": "combined content"}}
- {{"action": "delete", "id": "<uuid>", "reason": "why"}}

If two memories contradict each other, prefer the one supported by more recent evidence.

Current memories:
{memories}

Recent session summaries (newest first):
{sessions}

Return a JSON array of actions."""


async def should_consolidate(user_id: uuid.UUID) -> bool:
    """Check whether consolidation should run for this user."""
    async with async_session() as db:
        user = await db.get(User, user_id)
        if not user:
            return False

        last = user.last_memory_consolidation
        if last:
            hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600
            if hours_since < CONSOLIDATION_COOLDOWN_HOURS:
                return False

        session_count = await db.scalar(
            select(func.count(ChatSession.id)).where(
                ChatSession.user_id == user_id,
                ChatSession.created_at > (last or datetime.min.replace(tzinfo=timezone.utc)),
            )
        )
        return (session_count or 0) >= MIN_SESSIONS_BEFORE_CONSOLIDATION


async def consolidate_memories(user_id: uuid.UUID, llm) -> int:
    """Run memory consolidation for a user. Returns count of actions taken."""
    async with async_session() as db:
        memories = (await db.scalars(
            select(AgentMemory)
            .where(AgentMemory.user_id == user_id)
            .order_by(AgentMemory.updated_at.desc().nullsfirst(), AgentMemory.created_at.desc())
        )).all()

        if len(memories) < 3:
            logger.debug("Skipping consolidation for user %s: only %d memories", user_id, len(memories))
            return 0

        user = await db.get(User, user_id)
        last = user.last_memory_consolidation if user else None

        sessions = (await db.scalars(
            select(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.created_at > (last or datetime.min.replace(tzinfo=timezone.utc)),
            )
            .order_by(ChatSession.created_at.desc())
            .limit(10)
        )).all()

        memories_text = "\n\n".join(
            f"[{m.id}] type={m.type} name=\"{m.name}\"\n"
            f"  description: {m.description}\n"
            f"  content: {m.content}\n"
            f"  created: {m.created_at}, updated: {m.updated_at or 'never'}"
            for m in memories
        )

        sessions_text = "\n\n".join(
            f"Session {s.id} ({s.created_at.strftime('%Y-%m-%d %H:%M')}):\n"
            f"  {s.session_notes or s.context_summary or '(no summary)'}"
            for s in sessions
        ) or "(no recent sessions)"

        prompt = CONSOLIDATION_PROMPT.format(
            memories=memories_text, sessions=sessions_text,
        )

        try:
            response = await llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            start = content.find("[")
            end = content.rfind("]") + 1
            if start < 0 or end <= start:
                logger.warning("Consolidation returned no valid JSON array")
                return 0
            actions = json.loads(content[start:end])
        except Exception:
            logger.exception("Memory consolidation LLM call failed for user %s", user_id)
            return 0

        memory_map = {str(m.id): m for m in memories}
        action_count = 0

        for action in actions:
            act = action.get("action")
            mid = action.get("id")
            mem = memory_map.get(mid)

            if act == "keep" or mem is None:
                continue

            if act == "update":
                mem.content = action.get("content", mem.content)
                mem.description = action.get("description", mem.description)
                action_count += 1
                logger.debug("Consolidation: updated memory %s", mid)

            elif act == "merge":
                target_id = action.get("merge_into")
                target = memory_map.get(target_id)
                if target:
                    target.content = action.get("merged_content", target.content)
                    await db.delete(mem)
                    action_count += 1
                    logger.debug("Consolidation: merged %s into %s", mid, target_id)

            elif act == "delete":
                await db.delete(mem)
                action_count += 1
                logger.debug("Consolidation: deleted %s (%s)", mid, action.get("reason", ""))

        if user:
            user.last_memory_consolidation = datetime.now(timezone.utc)

        await db.commit()
        logger.info(
            "Memory consolidation for user %s: %d actions on %d memories",
            user_id, action_count, len(memories),
        )
        return action_count


async def maybe_consolidate(user_id: uuid.UUID, llm) -> None:
    """Check trigger conditions and run consolidation if warranted.

    Safe to call frequently -- the cooldown and session-count gates
    prevent unnecessary work.
    """
    try:
        if await should_consolidate(user_id):
            await consolidate_memories(user_id, llm)
    except Exception:
        logger.debug("Memory consolidation check failed (non-critical)", exc_info=True)
