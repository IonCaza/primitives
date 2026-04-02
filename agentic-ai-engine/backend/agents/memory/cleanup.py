"""Post-turn checkpoint cleanup: trims old messages and maintains a rolling summary.

After each agent turn, checks whether checkpoint messages exceed a threshold.
If they do, summarises the oldest messages and removes them from the checkpoint
via RemoveMessage, keeping the checkpoint lean.

Eviction is boundary-aware: it never splits a tool_call from its tool_response,
and the first kept message is always a human (user) message so the remaining
history forms a valid conversation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import RemoveMessage, BaseMessage

from app.agents.context.manager import (
    count_tokens,
    get_context_window,
    resolve_summary_limit,
)
from app.agents.context.summarizer import summarize_messages
from app.agents.settings_cache import get_memory_settings

if TYPE_CHECKING:
    from langgraph.prebuilt import create_react_agent
    from langchain_litellm import ChatLiteLLM
    from app.db.models.agent_config import AgentConfig
    from app.db.models.llm_provider import LlmProvider

logger = logging.getLogger(__name__)


def _msg_to_dict(msg: BaseMessage) -> dict:
    role = "assistant"
    if msg.type == "human":
        role = "user"
    elif msg.type == "system":
        role = "system"
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    return {"role": role, "content": content}


def _find_safe_eviction_boundary(messages: list[BaseMessage], target_keep: int) -> int:
    """Return the index where eviction should stop (first kept message).

    Ensures the boundary doesn't split a tool_call/tool_response pair and that
    the first kept message is a human message (valid conversation start).
    """
    raw_boundary = len(messages) - target_keep

    boundary = raw_boundary
    while boundary < len(messages):
        msg = messages[boundary]
        if msg.type == "human":
            break
        boundary += 1

    if boundary >= len(messages) - 2:
        return raw_boundary

    return boundary


async def cleanup_checkpoint(
    agent,
    config: dict,
    llm: "ChatLiteLLM",
    agent_config: "AgentConfig",
    provider: "LlmProvider",
    *,
    force: bool = False,
) -> None:
    """Trim checkpoint messages if they exceed the context-window threshold.

    When *force* is True the threshold check is skipped, evicting aggressively.
    This is used by the reactive-recovery path after a prompt-too-long error.
    """
    try:
        snapshot = await agent.aget_state(config)
    except Exception:
        logger.debug("No checkpoint state to clean up")
        return

    if not snapshot or not snapshot.values:
        return

    messages: list[BaseMessage] = snapshot.values.get("messages", [])
    existing_summary: str | None = snapshot.values.get("context_summary")

    if len(messages) < 6:
        return

    settings = await get_memory_settings()

    model = provider.model
    ctx_window = get_context_window(provider)
    threshold = int(ctx_window * settings.cleanup_threshold_ratio)

    total_tokens = sum(
        count_tokens(model, m.content if isinstance(m.content, str) else str(m.content)) + 4
        for m in messages
    )
    if not force and total_tokens <= threshold:
        return

    if force:
        logger.warning("Emergency compaction triggered (force=True, %d tokens, %d messages)", total_tokens, len(messages))

    target_keep = max(4, len(messages) // 2)
    boundary = _find_safe_eviction_boundary(messages, target_keep)
    evicted = messages[:boundary]
    if not evicted:
        return

    logger.info(
        "Checkpoint cleanup: evicting %d of %d messages (%d tokens > %d threshold), "
        "first kept message type=%s",
        len(evicted), len(messages), total_tokens, threshold,
        messages[boundary].type if boundary < len(messages) else "none",
    )

    session_notes: str | None = snapshot.values.get("session_notes")

    if session_notes:
        new_summary = f"## Structured Session Notes\n{session_notes}"
        logger.info("Using session notes as compaction summary (skipping LLM call)")
    else:
        summary_limit = resolve_summary_limit(agent_config, ctx_window, settings.summary_token_ratio)
        evicted_dicts = [_msg_to_dict(m) for m in evicted]

        try:
            new_summary = await summarize_messages(
                llm, evicted_dicts, existing_summary, summary_limit,
            )
        except Exception:
            logger.exception("Checkpoint summarization failed, keeping messages")
            return

    remove_ops = [RemoveMessage(id=m.id) for m in evicted if hasattr(m, "id") and m.id]
    update: dict = {"context_summary": new_summary}
    if remove_ops:
        update["messages"] = remove_ops

    try:
        await agent.aupdate_state(config, update)
        logger.info("Checkpoint trimmed: removed %d messages, summary updated", len(remove_ops))
    except Exception:
        logger.exception("Failed to update checkpoint state")
