"""Prompt callable that trims checkpoint messages to fit the context window.

Plugged into create_react_agent as ``prompt``. Runs before every LLM call
within a turn: receives the full accumulated state and returns a message
list that fits within the token budget.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Sequence

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

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
        messages: Sequence[BaseMessage] = state.get("messages", [])
        summary: str | None = state.get("context_summary")

        budget = ctx_window - system_tokens - RESPONSE_RESERVE - SCRATCHPAD_RESERVE
        if summary:
            budget -= count_tokens(model, summary) + 4

        if budget <= 0:
            result = [SystemMessage(content=system_prompt)]
            if summary:
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
        if summary:
            result.append(
                SystemMessage(content=f"Previous conversation context:\n{summary}")
            )
        result.extend(keep)
        return _strip_thinking_blocks(result)

    return _modifier
