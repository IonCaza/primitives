from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

if TYPE_CHECKING:
    from langchain_litellm import ChatLiteLLM

SUMMARIZATION_PROMPT = """\
You are a conversation summarizer. Condense the conversation below into a \
structured summary that another AI assistant can use to continue the \
conversation seamlessly.

Target approximately {target_tokens} tokens. Be concise but preserve every \
important detail.

Use this exact structure:

## Conversation Summary

### Key Topics
- List each distinct topic discussed with a one-line description.

### Decisions and Conclusions
- What was decided, agreed upon, or concluded.

### Important Entities and Context
- Specific names, IDs, numbers, technical details, or references that may \
be needed later.

### Current State
- What the user is currently working on or asking about.
- Any pending questions or unresolved threads.

{prior_summary_instruction}

---

CONVERSATION TO SUMMARIZE:
{conversation}"""

PRIOR_SUMMARY_INSTRUCTION = """\
A prior summary of even older messages is included below. Incorporate its \
key points into your new summary -- do not simply append it. Merge and \
deduplicate information.

PRIOR SUMMARY:
{prior_summary}"""


def _format_messages(messages: list[dict]) -> str:
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        parts.append(f"[{role}]: {content}")
    return "\n\n".join(parts)


async def summarize_messages(
    llm: ChatLiteLLM,
    messages: list[dict],
    existing_summary: str | None,
    target_tokens: int,
) -> str:
    """Produce a structured summary of the given messages."""
    conversation_text = _format_messages(messages)

    if existing_summary:
        prior_instruction = PRIOR_SUMMARY_INSTRUCTION.format(
            prior_summary=existing_summary,
        )
    else:
        prior_instruction = ""

    prompt_text = SUMMARIZATION_PROMPT.format(
        target_tokens=target_tokens,
        prior_summary_instruction=prior_instruction,
        conversation=conversation_text,
    )

    response = await llm.ainvoke(
        [
            SystemMessage(content="You are a precise conversation summarizer."),
            HumanMessage(content=prompt_text),
        ],
    )
    return response.content
