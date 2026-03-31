"""Long-term memory tools: save and search memories across sessions."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool

from app.agents.memory.pool import get_store

logger = logging.getLogger(__name__)


def build_memory_tools(user_id: uuid.UUID) -> list:
    """Return save_memory and search_memory tools scoped to a user.

    If the store is not configured (no embedding provider), returns an
    empty list so agents silently operate without long-term memory.
    """
    store = get_store()
    if store is None:
        return []

    namespace = ("memories", str(user_id))

    @tool
    async def save_memory(content: str, tags: str = "") -> str:
        """Save an important fact, decision, or user preference to long-term memory.

        Use this when the user states a preference, makes a decision, or when you
        learn something important that should be remembered across conversations.

        Args:
            content: The fact or insight to remember.
            tags: Comma-separated tags for categorisation (e.g. "preference,project-x").
        """
        try:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
            key = str(uuid.uuid4())
            await store.aput(
                namespace,
                key,
                {
                    "text": content,
                    "tags": tag_list,
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return f"Memory saved (key={key[:8]}...)."
        except Exception:
            logger.exception("Failed to save memory")
            return "Failed to save memory — the store may not be configured."

    @tool
    async def search_memory(query: str, limit: int = 5) -> str:
        """Search long-term memory for facts, decisions, or preferences from past conversations.

        Use this at the start of a conversation to recall relevant context,
        or when the user references something from a previous session.

        Args:
            query: Natural-language search query.
            limit: Maximum number of results (default 5).
        """
        try:
            results = await store.asearch(namespace, query=query, limit=limit)
            if not results:
                return "No matching memories found."
            lines = []
            for item in results:
                val = item.value
                text = val.get("text", "")
                tags = val.get("tags", [])
                saved = val.get("saved_at", "")
                tag_str = f" [{', '.join(tags)}]" if tags else ""
                lines.append(f"- {text}{tag_str} (saved: {saved})")
            return "Matching memories:\n" + "\n".join(lines)
        except Exception:
            logger.exception("Failed to search memory")
            return "Failed to search memory — the store may not be configured."

    return [save_memory, search_memory]
