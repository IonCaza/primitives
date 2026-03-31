"""Platform-level tool for searching chat session history.

Injected dynamically into every agent by the runner -- not part of the
assignable tool registry.

Uses an independent database session per invocation to avoid conflicts
with the agent's main session (which may be mid-query when tools run
concurrently).
"""
from __future__ import annotations

import logging
import uuid

from langchain_core.tools import tool
from sqlalchemy import select

from app.db.base import async_session
from app.db.models.chat import ChatMessage

logger = logging.getLogger(__name__)

MAX_RESULTS = 15
MAX_CONTENT_LEN = 500


def build_search_chat_history_tool(
    session_id: uuid.UUID,
):
    """Return a @tool bound to a specific chat session."""

    @tool
    async def search_chat_history(query: str) -> str:
        """Search the full chat history for this session.

        Use this to find specific details from earlier in the conversation
        that may not be in your current context. Accepts a keyword or phrase
        and returns matching messages with timestamps.
        """
        async with async_session() as db:
            pattern = f"%{query}%"
            result = await db.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.content.ilike(pattern),
                )
                .order_by(ChatMessage.created_at.desc())
                .limit(MAX_RESULTS)
            )
            rows = result.scalars().all()

            if not rows:
                return f"No messages found matching '{query}' in this session's history."

            parts: list[str] = []
            for msg in reversed(rows):
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M UTC")
                content = msg.content
                if len(content) > MAX_CONTENT_LEN:
                    content = content[:MAX_CONTENT_LEN] + "..."
                parts.append(f"[{ts}] [{msg.role.value.upper()}]: {content}")

            header = f"Found {len(rows)} matching message(s) for '{query}':\n\n"
            return header + "\n\n".join(parts)

    return search_chat_history
