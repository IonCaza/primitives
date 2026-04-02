"""Multi-stage prompt callable that fits checkpoint messages into the context window.

Plugged into create_react_agent as ``prompt``. Runs before every LLM call
within a turn.  The pipeline applies cheap transformations first (budgeting,
microcompact) before falling back to the more aggressive trim-from-front.

Stages:
  1. **Budget tool results** -- cap any single ToolMessage to MAX_TOOL_RESULT_TOKENS.
  2. **Microcompact** -- replace old read-only tool results with placeholders.
  3. **Trim from back** -- drop oldest messages until we fit the token budget.
  4. (Reactive recovery lives in the runner, not here.)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Sequence

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage

from app.agents.context.manager import (
    RESPONSE_RESERVE,
    SCRATCHPAD_RESERVE,
    count_tokens,
    get_context_window,
)

if TYPE_CHECKING:
    from app.db.models.agent_config import AgentConfig
    from app.db.models.llm_provider import LlmProvider

logger = logging.getLogger(__name__)

MAX_TOOL_RESULT_TOKENS = 2500

COMPACTABLE_TOOLS = frozenset({
    "run_sql_query",
    "list_tables",
    "describe_table",
    "search_memories",
    "search_chat_history",
    "get_presentation_template",
    "get_presentation",
    "list_tasks",
    "get_task",
})
KEEP_RECENT_RESULTS = 5


def _budget_tool_results(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Stage 1: cap oversized tool results so one large query can't dominate."""
    result: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if len(content) // 4 > MAX_TOOL_RESULT_TOKENS:
                char_limit = MAX_TOOL_RESULT_TOKENS * 4
                truncated = content[:char_limit] + "\n[... result truncated to fit context ...]"
                result.append(ToolMessage(
                    content=truncated,
                    tool_call_id=getattr(msg, "tool_call_id", ""),
                    name=getattr(msg, "name", ""),
                ))
                continue
        result.append(msg)
    return result


def _microcompact(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Stage 2: replace old read-only tool results with lightweight placeholders."""
    tool_indices = [
        i for i, m in enumerate(messages)
        if isinstance(m, ToolMessage) and getattr(m, "name", "") in COMPACTABLE_TOOLS
    ]
    if len(tool_indices) <= KEEP_RECENT_RESULTS:
        return messages

    to_clear = set(tool_indices[:-KEEP_RECENT_RESULTS])
    result: list[BaseMessage] = []
    for i, msg in enumerate(messages):
        if i in to_clear:
            m = msg  # type: ToolMessage
            result.append(ToolMessage(
                content=f"[Previous {getattr(m, 'name', 'tool')} result cleared to save context]",
                tool_call_id=getattr(m, "tool_call_id", ""),
                name=getattr(m, "name", ""),
            ))
        else:
            result.append(msg)
    return result


def _msg_text(msg: BaseMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    return str(msg.content)


def _strip_thinking_blocks(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Remove ``thinking`` content blocks from AI messages.

    Anthropic's extended-thinking API requires a ``signature`` field on
    thinking blocks when they appear in conversation history.  LangChain's
    message serialisation does not preserve this field, so replayed
    thinking blocks cause ``400 Bad Request`` errors.  Stripping them is
    safe because thinking is already captured during streaming.
    """
    cleaned: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, AIMessage) and isinstance(msg.content, list):
            new_content = [
                block for block in msg.content
                if not (isinstance(block, dict) and block.get("type") == "thinking")
            ]
            if len(new_content) != len(msg.content):
                msg = msg.model_copy(update={
                    "content": new_content if new_content else "",
                })
        cleaned.append(msg)
    return cleaned


def make_state_modifier(
    system_prompt: str,
    agent_config: "AgentConfig",
    provider: "LlmProvider",
):
    """Return a callable that trims messages for the LLM's context window."""
    model = provider.model
    ctx_window = get_context_window(provider)
    system_tokens = count_tokens(model, system_prompt)

    async def _modifier(state: dict) -> list[BaseMessage]:
        messages: list[BaseMessage] = list(state.get("messages", []))
        summary: str | None = state.get("context_summary")
        session_notes: str | None = state.get("session_notes")

        messages = _budget_tool_results(messages)
        messages = _microcompact(messages)

        budget = ctx_window - system_tokens - RESPONSE_RESERVE - SCRATCHPAD_RESERVE
        if summary:
            budget -= count_tokens(model, summary) + 4
        if session_notes:
            budget -= count_tokens(model, session_notes) + 4

        if budget <= 0:
            result = [SystemMessage(content=system_prompt)]
            if session_notes:
                result.append(SystemMessage(content=session_notes))
            elif summary:
                result.append(SystemMessage(content=f"Previous conversation context:\n{summary}"))
            if messages:
                result.append(messages[-1])
            return _strip_thinking_blocks(result)

        keep: list[BaseMessage] = []
        keep_tokens = 0
        for msg in reversed(messages):
            tok = count_tokens(model, _msg_text(msg)) + 4
            if keep_tokens + tok > budget:
                break
            keep.insert(0, msg)
            keep_tokens += tok

        result: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        if session_notes:
            result.append(SystemMessage(content=session_notes))
        if summary:
            result.append(
                SystemMessage(content=f"Previous conversation context:\n{summary}")
            )
        result.extend(keep)
        return _strip_thinking_blocks(result)

    return _modifier
