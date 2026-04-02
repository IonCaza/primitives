"""Session notes: a structured document maintained throughout the conversation.

Unlike the rolling context_summary (regenerated from scratch on each
compaction), session notes are incrementally updated and preserved across
compaction events.  They capture decisions, errors, corrections, and
current working state in a dense, queryable format.

Extraction is triggered after a turn when enough new material has
accumulated (token + tool-call thresholds).
"""

from __future__ import annotations

import logging
import uuid

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session
from app.db.models.chat import ChatSession

logger = logging.getLogger(__name__)

NEW_TOKEN_THRESHOLD = 8_000
MIN_TOOL_CALLS = 2

SESSION_NOTES_TEMPLATE = """\
# Session Notes

## Current Focus
_What is actively being worked on or discussed right now._

## User's Request
_What the user originally asked for. Key constraints and preferences._

## Data Landscape
_Which tables, columns, and queries are relevant. What the data looks like._

## Agent Activity
_Which agents were delegated to and what they found. Key results from each._

## Corrections and Adjustments
_Things the user corrected. Approaches that failed and why._

## Insights
_Non-obvious findings. What worked well. What to avoid next time._

## Deliverables
_Final outputs, numbers, or artifacts produced for the user._
"""

NOTES_EXTRACTION_PROMPT = """\
Update the session notes below based on the recent conversation.

Rules:
- Preserve all section headers exactly as they are
- Only modify the content under each section, not the headers or descriptions
- Write dense, specific content -- include exact table names, column names, \
query snippets, and numbers rather than vague summaries
- Keep each section under 400 words
- Always update "Current Focus" to reflect the most recent activity
- In "Corrections", record both what was wrong and what the right answer was
- If a section has no relevant updates, leave its existing content unchanged

Current notes:
{current_notes}

Recent conversation to incorporate:
{recent_messages}
"""


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _msg_text(msg: BaseMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    return str(msg.content)


async def maybe_update_session_notes(
    session_id: uuid.UUID,
    messages: list[BaseMessage],
    current_notes: str | None,
    cursor: int,
    llm,
) -> str | None:
    """Check thresholds and update session notes if warranted.

    Returns the updated notes string, or None if no update was performed.
    """
    new_messages = messages[cursor:]
    if not new_messages:
        return None

    new_tokens = sum(_estimate_tokens(_msg_text(m)) for m in new_messages)
    tool_calls = sum(1 for m in new_messages if isinstance(m, ToolMessage))

    if new_tokens < NEW_TOKEN_THRESHOLD or tool_calls < MIN_TOOL_CALLS:
        return None

    notes = current_notes or SESSION_NOTES_TEMPLATE

    recent_text = _format_messages_for_extraction(new_messages)

    try:
        result = await llm.ainvoke([
            SystemMessage(content="You maintain structured session notes. Be concise and specific."),
            HumanMessage(content=NOTES_EXTRACTION_PROMPT.format(
                current_notes=notes,
                recent_messages=recent_text,
            )),
        ])

        updated_notes = result.content
        if not updated_notes or len(updated_notes) < 50:
            return None

        await _persist_notes(session_id, updated_notes, len(messages))

        logger.info(
            "Session notes updated for session %s (cursor %d -> %d, %d new tokens, %d tool calls)",
            session_id, cursor, len(messages), new_tokens, tool_calls,
        )
        return updated_notes
    except Exception:
        logger.debug("Session notes extraction failed (non-critical)", exc_info=True)
        return None


def _format_messages_for_extraction(messages: list[BaseMessage], max_chars: int = 30_000) -> str:
    """Format messages into a readable text block for the extraction LLM."""
    lines = []
    total = 0
    for msg in messages:
        role = msg.type
        text = _msg_text(msg)
        if isinstance(msg, ToolMessage):
            name = getattr(msg, "name", "tool")
            text = text[:2000] if len(text) > 2000 else text
            line = f"[{name}]: {text}"
        else:
            line = f"{role}: {text}"

        if total + len(line) > max_chars:
            lines.append("[... earlier messages trimmed ...]")
            break
        lines.append(line)
        total += len(line)

    return "\n\n".join(lines)


async def _persist_notes(
    session_id: uuid.UUID, notes: str, cursor: int
) -> None:
    """Write updated notes and cursor to the ChatSession row."""
    async with async_session() as db:
        await db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(session_notes=notes, notes_token_cursor=cursor)
        )
        await db.commit()


async def load_session_notes(
    session_id: uuid.UUID,
) -> tuple[str | None, int]:
    """Load existing session notes and cursor from the database."""
    async with async_session() as db:
        row = (
            await db.execute(
                select(
                    ChatSession.session_notes,
                    ChatSession.notes_token_cursor,
                ).where(ChatSession.id == session_id)
            )
        ).one_or_none()
        if row is None:
            return None, 0
        return row[0], row[1] or 0
