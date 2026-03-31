from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import litellm

if TYPE_CHECKING:
    from app.db.models.agent_config import AgentConfig
    from app.db.models.llm_provider import LlmProvider
    from langchain_litellm import ChatLiteLLM

from app.agents.context.summarizer import summarize_messages

logger = logging.getLogger(__name__)

RESPONSE_RESERVE = 4096
SCRATCHPAD_RESERVE = 2048
DEFAULT_CONTEXT_WINDOW = 8192


def get_context_window(provider: LlmProvider) -> int:
    """Resolve the context window for a provider.

    Priority: litellm auto-detect -> provider.context_window -> 8192 fallback.
    """
    try:
        info = litellm.get_model_info(provider.model)
        max_input = info.get("max_input_tokens") or info.get("max_tokens")
        if max_input and isinstance(max_input, int) and max_input > 0:
            return max_input
    except Exception:
        logger.debug("Could not auto-detect context window for %s", provider.model)

    if provider.context_window and provider.context_window > 0:
        return provider.context_window

    return DEFAULT_CONTEXT_WINDOW


def auto_summary_limit(context_window: int, ratio: float = 0.04) -> int:
    """Scale the summary token target to a fraction of the context window, clamped 500-8192."""
    return max(500, min(int(context_window * ratio), 8192))


def resolve_summary_limit(agent_config: AgentConfig, context_window: int, ratio: float = 0.04) -> int:
    if agent_config.summary_token_limit and agent_config.summary_token_limit > 0:
        return agent_config.summary_token_limit
    return auto_summary_limit(context_window, ratio)


def count_tokens(model: str, text: str) -> int:
    try:
        return litellm.token_counter(model=model, text=text)
    except Exception:
        return len(text) // 4


def count_messages_tokens(model: str, messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        total += count_tokens(model, msg.get("content", ""))
        total += 4  # per-message overhead (role, separators)
    return total


async def prepare_history(
    agent_config: AgentConfig,
    provider: LlmProvider,
    llm: ChatLiteLLM,
    system_prompt: str,
    user_input: str,
    chat_history: list[dict],
    existing_summary: str | None,
) -> tuple[list[dict], str | None]:
    """Trim chat history to fit the context window, summarizing if needed.

    Returns (trimmed_history, new_summary_or_None).
    """
    model = provider.model
    ctx_window = get_context_window(provider)
    summary_limit = resolve_summary_limit(agent_config, ctx_window)

    system_tokens = count_tokens(model, system_prompt)
    input_tokens = count_tokens(model, user_input)
    fixed_overhead = system_tokens + input_tokens + RESPONSE_RESERVE + SCRATCHPAD_RESERVE
    history_budget = ctx_window - fixed_overhead

    if history_budget <= 0:
        logger.warning(
            "System prompt + input already exceeds context window "
            "(%d tokens fixed vs %d window). Sending with no history.",
            fixed_overhead, ctx_window,
        )
        return [], None

    history_tokens = count_messages_tokens(model, chat_history)
    if history_tokens <= history_budget:
        return chat_history, None

    keep: list[dict] = []
    keep_tokens = 0
    for msg in reversed(chat_history):
        msg_tokens = count_tokens(model, msg.get("content", "")) + 4
        if keep_tokens + msg_tokens > history_budget:
            break
        keep.insert(0, msg)
        keep_tokens += msg_tokens

    evicted = chat_history[: len(chat_history) - len(keep)]
    if not evicted:
        return chat_history, None

    logger.info(
        "Context management: evicting %d messages (%d tokens), "
        "keeping %d messages (%d tokens), budget=%d",
        len(evicted), history_tokens - keep_tokens,
        len(keep), keep_tokens, history_budget,
    )

    try:
        new_summary = await summarize_messages(
            llm, evicted, existing_summary, summary_limit,
        )
    except Exception:
        logger.exception("Summarization failed, falling back to truncation")
        new_summary = existing_summary

    summary_msg: list[dict] = []
    if new_summary:
        summary_msg = [{"role": "assistant", "content": new_summary}]

    return summary_msg + keep, new_summary
