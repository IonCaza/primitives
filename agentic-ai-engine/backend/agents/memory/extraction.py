"""Background memory extraction with taxonomy awareness.

After each agent turn, a fast LLM reviews the conversation and decides
whether to save, update, or delete structured memories in the AgentMemory
table.  Dual-writes to the vector store for semantic search support.
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select

from app.agents.memory.pool import get_store
from app.db.base import async_session
from app.db.models.agent_memory import AgentMemory
from app.db.models.ai_settings import AiSettings, SINGLETON_ID

logger = logging.getLogger(__name__)

_llm_cache: dict[str, object] = {}

EXTRACTION_PROMPT = """\
Review the conversation below and identify any information worth remembering
for future sessions. Use the four-type taxonomy:

- **user**: Preferences, expertise, communication style, role
- **feedback**: Corrections the user made, approaches they approved or rejected
- **project**: Business context, deadlines, team structure, decisions
- **reference**: Pointers to external systems, data sources, processes

Focus on:
- Things the user corrected or confirmed
- Preferences they expressed (explicitly or implicitly)
- Business context that wouldn't be obvious from the data alone
- References to external systems or processes

Skip:
- Database schema information (queryable on demand)
- Specific data values that change frequently (query the source)
- One-time task details with no future relevance
- Information that is already captured in existing memories

For each action, output a JSON array. Examples:
[
  {"action": "save", "name": "revenue-metric-preference", "description": "User prefers net_amount over gross for revenue", "type": "feedback", "content": "When calculating revenue, use net_amount column not gross_amount. Confirmed after Q3 discrepancy."},
  {"action": "update", "id": "abc123...", "content": "Updated content here"},
  {"action": "delete", "id": "abc123...", "reason": "No longer relevant"}
]

If nothing is worth remembering, return: []

Existing memories for context:
{existing_memories}

Conversation:
{conversation}
"""


async def _resolve_extraction_model() -> str | None:
    """Read AiSettings to determine the extraction model string."""
    try:
        async with async_session() as db:
            row = (await db.execute(
                select(AiSettings).where(AiSettings.id == SINGLETON_ID)
            )).scalar_one_or_none()

            if not row or not row.extraction_enabled:
                return None

            if not row.extraction_provider_id:
                return None

            from app.db.models.llm_provider import LlmProvider
            provider = (await db.execute(
                select(LlmProvider).where(LlmProvider.id == row.extraction_provider_id)
            )).scalar_one_or_none()

            if not provider:
                return None

            return provider.model
    except Exception:
        logger.debug("Failed to resolve extraction model", exc_info=True)
        return None


async def _get_extraction_llm():
    """Lazy-init a lightweight LLM for extraction."""
    model = await _resolve_extraction_model()
    if not model:
        return None

    if model in _llm_cache:
        return _llm_cache[model]

    try:
        from langchain_litellm import ChatLiteLLM
        llm = ChatLiteLLM(model=model, temperature=0, max_tokens=2000)
        _llm_cache[model] = llm
        return llm
    except Exception:
        logger.debug("Failed to init extraction LLM", exc_info=True)
        return None


def invalidate_extraction_cache() -> None:
    """Force the LLM to be rebuilt on next call."""
    _llm_cache.clear()


async def extract_memories(
    user_id: uuid.UUID,
    messages: list[dict],
) -> None:
    """Extract memories from a turn's messages in the background.

    Reviews the conversation against existing memories and decides what
    to save, update, or delete using the taxonomy.
    """
    llm = await _get_extraction_llm()
    if llm is None:
        return

    try:
        async with async_session() as db:
            existing = (await db.execute(
                select(AgentMemory)
                .where(AgentMemory.user_id == user_id)
                .order_by(AgentMemory.created_at.desc())
                .limit(50)
            )).scalars().all()

            existing_text = "\n".join(
                f"- [{m.type}] {m.name} (id={m.id}): {m.description}"
                for m in existing
            ) if existing else "(no existing memories)"

            conversation = "\n".join(
                f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                for msg in messages
            )

            prompt = EXTRACTION_PROMPT.format(
                existing_memories=existing_text,
                conversation=conversation,
            )

            from langchain_core.messages import HumanMessage
            result = await llm.ainvoke([HumanMessage(content=prompt)])

            actions = _parse_actions(result.content)
            if not actions:
                return

            existing_by_id = {str(m.id): m for m in existing}
            store = get_store()
            store_ns = ("memories", str(user_id))
            saved_memories: list[AgentMemory] = []
            deleted_ids: list[str] = []

            for action in actions:
                act = action.get("action")
                if act == "save":
                    mem_type = action.get("type", "")
                    if mem_type not in {"user", "feedback", "project", "reference"}:
                        continue
                    memory = AgentMemory(
                        user_id=user_id,
                        name=action.get("name", "untitled")[:200],
                        description=action.get("description", "")[:500],
                        type=mem_type,
                        content=action.get("content", ""),
                    )
                    db.add(memory)
                    saved_memories.append(memory)
                elif act == "update":
                    mid = action.get("id", "")
                    target = existing_by_id.get(mid)
                    if target and action.get("content"):
                        target.content = action["content"]
                        if action.get("description"):
                            target.description = action["description"][:500]
                        saved_memories.append(target)
                elif act == "delete":
                    mid = action.get("id", "")
                    target = existing_by_id.get(mid)
                    if target:
                        await db.delete(target)
                        deleted_ids.append(mid)

            await db.commit()

            if store is not None:
                for mem in saved_memories:
                    try:
                        await store.aput(store_ns, str(mem.id), {
                            "text": mem.content,
                            "name": mem.name,
                            "type": mem.type,
                            "description": mem.description,
                        })
                    except Exception:
                        logger.debug("Store mirror failed for %s", mem.id, exc_info=True)
                for mid in deleted_ids:
                    try:
                        await store.adelete(store_ns, mid)
                    except Exception:
                        logger.debug("Store delete failed for %s", mid, exc_info=True)

            logger.debug("Extraction completed for user %s: %d actions", user_id, len(actions))
    except Exception:
        logger.debug("Memory extraction failed (non-critical)", exc_info=True)


def _parse_actions(text: str) -> list[dict]:
    """Parse the LLM's JSON response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "actions" in parsed:
            return parsed["actions"]
    except json.JSONDecodeError:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return []
