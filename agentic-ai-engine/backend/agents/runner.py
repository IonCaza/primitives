from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import build_agent
from app.agents.context import current_session_id, current_user_id, current_entitlements
from app.agents.context.resolver import get_entitlement_resolver
from app.agents.coordinator import build_coordinator
from app.agents.llm.manager import build_llm_from_provider
from app.agents.memory.cleanup import cleanup_checkpoint
from app.agents.memory.extraction import extract_memories
from app.agents.memory.recall import recall_relevant_memories, format_recalled_for_prompt
from app.agents.skills import load_active_skills
from app.agents.memory.consolidation import maybe_consolidate
from app.agents.memory.session_notes import load_session_notes, maybe_update_session_notes
from app.agents.memory.tools import build_memory_tools
from app.agents.settings_cache import get_memory_settings
from app.agents.supervisor import build_delegation_tools, build_prompt_management_tools
from app.agents.registry import is_ai_enabled, get_agent_by_slug
from app.agents.tools.chat_history import build_search_chat_history_tool
from app.agents.tools.feedback_gap import build_report_capability_gap_tool
from app.agents.tools.task_tools import build_task_tools
from app.db.models.llm_provider import LlmProvider

logger = logging.getLogger(__name__)

DELEGATION_PREFIX = "ask_"


async def run_agent_stream(
    db: AsyncSession,
    user_input: str,
    agent_slug: str = "contribution-analyst",
    *,
    session_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    attachments: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run a named agent and yield structured event dicts.

    Event types:
        {"type": "token", "content": str}
        {"type": "thinking", "content": str}
        {"type": "agent_start", "run_id": str, "slug": str, "query": str}
        {"type": "agent_token", "run_id": str, "content": str}
        {"type": "agent_done", "run_id": str}
        {"type": "tool_call_start", "run_id": str, "tool_name": str, "args": dict}
        {"type": "tool_call_end", "run_id": str, "tool_name": str, "result": str}
        {"type": "task_update", "session_id": str}
        {"type": "presentation_update", "presentation_id": str}

    The checkpointer handles message history natively via thread_id.
    Only the new user message is passed in; all prior context is loaded
    from the checkpoint automatically.
    """
    if not await is_ai_enabled(db):
        raise RuntimeError("AI is not enabled")

    agent_config = await get_agent_by_slug(db, agent_slug)
    if not agent_config:
        raise RuntimeError(f"Agent '{agent_slug}' not found or not enabled")

    provider: LlmProvider | None = agent_config.llm_provider
    if not provider:
        result = await db.execute(
            select(LlmProvider)
            .where(LlmProvider.is_default.is_(True))
            .where(LlmProvider.model_type == "chat")
            .limit(1)
        )
        provider = result.scalar_one_or_none()
    if not provider:
        result = await db.execute(
            select(LlmProvider).where(LlmProvider.model_type == "chat").limit(1)
        )
        provider = result.scalar_one_or_none()
    if not provider:
        raise RuntimeError("No LLM provider available — configure one in Settings > AI")

    mem_settings = await get_memory_settings()

    extra_tools = []
    if session_id is not None:
        extra_tools.append(build_search_chat_history_tool(session_id))
        extra_tools.append(build_report_capability_gap_tool(session_id, agent_slug))
        extra_tools.extend(build_task_tools(db, session_id))
    if user_id is not None and mem_settings.memory_enabled:
        extra_tools.extend(build_memory_tools(user_id))

    is_supervisor = getattr(agent_config, "agent_type", "standard") == "supervisor"
    if is_supervisor:
        member_agents = getattr(agent_config, "member_agents", [])
        if member_agents:
            delegation_tools = build_delegation_tools(member_agents, provider)
            extra_tools.extend(delegation_tools)
            extra_tools.extend(build_prompt_management_tools(member_agents))
            logger.info(
                "Supervisor %s: %d delegation tools for members %s",
                agent_slug,
                len(delegation_tools),
                [m.slug for m in member_agents],
            )

    current_user_id.set(user_id)
    current_session_id.set(session_id)

    # Resolve RBAC entitlements for the calling user
    entitlements = None
    if user_id is not None:
        try:
            resolver = get_entitlement_resolver()
            entitlements = await resolver.resolve(db, user_id)
            current_entitlements.set(entitlements)
        except Exception:
            logger.debug("Entitlement resolution failed (non-critical, defaulting to open)", exc_info=True)

    if entitlements and not entitlements.can_invoke_agent(agent_slug):
        yield {"type": "error", "content": f"You do not have access to the {agent_config.name} agent."}
        return

    recalled_context = ""
    if user_id and mem_settings.memory_enabled:
        try:
            recall_llm = build_llm_from_provider(provider, streaming=False)
            recalled = await recall_relevant_memories(db, user_id, user_input, recall_llm)
            recalled_context = format_recalled_for_prompt(recalled)
            if recalled_context:
                logger.info("Recalled %d memories for user %s", len(recalled), user_id)
        except Exception:
            logger.debug("Memory recall pre-flight failed (non-critical)", exc_info=True)

    skill_context = ""
    try:
        skill_context = await load_active_skills(agent_slug, db)
        if skill_context:
            logger.info("Loaded skills for agent %s", agent_slug)
    except Exception:
        logger.debug("Skill loading failed (non-critical)", exc_info=True)

    if is_supervisor:
        agent, max_iterations = build_coordinator(
            agent_config, provider, db, extra_tools=extra_tools,
            recalled_context=recalled_context,
            skill_context=skill_context,
        )
    else:
        agent, max_iterations = build_agent(
            agent_config, provider, db, extra_tools=extra_tools,
            recalled_context=recalled_context,
            skill_context=skill_context,
        )

    thread_id = str(session_id) if session_id else str(uuid.uuid4())
    run_config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": (max_iterations or (50 if is_supervisor else 25)) * 2,
    }

    try:
        snapshot = await agent.aget_state(run_config)
        if snapshot and snapshot.values:
            msgs = snapshot.values.get("messages", [])
            orphaned = []
            tool_msg_call_ids = {
                getattr(m, "tool_call_id", None) for m in msgs if m.type == "tool"
            }
            for m in msgs:
                if m.type == "ai" and getattr(m, "tool_calls", None):
                    for tc in m.tool_calls:
                        if tc.get("id") and tc["id"] not in tool_msg_call_ids:
                            orphaned.append(tc)
            if orphaned:
                logger.warning(
                    "Repairing %d orphaned tool_calls in checkpoint %s",
                    len(orphaned), thread_id,
                )
                repair_msgs = [
                    ToolMessage(
                        content="[Tool call interrupted — no result available]",
                        tool_call_id=tc["id"],
                        name=tc.get("name", "unknown"),
                    )
                    for tc in orphaned
                ]
                await agent.aupdate_state(
                    run_config, {"messages": repair_msgs}
                )
    except Exception:
        logger.debug("Pre-flight checkpoint repair skipped", exc_info=True)

    notes_cursor = 0
    existing_notes: str | None = None
    if session_id:
        try:
            existing_notes, notes_cursor = await load_session_notes(session_id)
            if existing_notes:
                await agent.aupdate_state(run_config, {"session_notes": existing_notes})
        except Exception:
            logger.debug("Session notes pre-load failed (non-critical)", exc_info=True)

    active_delegations: dict[str, dict[str, str]] = {}
    _PRES_TOOLS = {"save_presentation", "update_presentation"}
    _TASK_TOOLS = {"create_task", "update_task"}
    pending_pres_ids: dict[str, str] = {}
    collected = ""
    pending_separator = False

    if attachments:
        content_parts: list[dict[str, Any]] = []
        if user_input:
            content_parts.append({"type": "text", "text": user_input})
        for att in attachments:
            if att["type"] == "image":
                content_parts.append(
                    {"type": "image_url", "image_url": {"url": att["data"]}}
                )
            elif att["type"] == "text":
                content_parts.append({"type": "text", "text": att["data"]})
        stream_input = {"messages": [HumanMessage(content=content_parts)]}
    else:
        stream_input = {"messages": [HumanMessage(content=user_input)]}

    async def _consume_stream(attempt: int = 1):
        nonlocal collected, pending_separator
        async for event in agent.astream_events(
            stream_input,
            version="v2",
            config=run_config,
        ):
            kind = event["event"]
            name = event.get("name", "")
            run_id = event.get("run_id", "")
            parent_ids: list[str] = event.get("parent_ids", [])

            if kind == "on_tool_start" and name.startswith(DELEGATION_PREFIX):
                slug = name[len(DELEGATION_PREFIX):].replace("_", "-")
                tool_input = event.get("data", {}).get("input", {})
                query_text = ""
                if isinstance(tool_input, dict):
                    query_text = tool_input.get("query", "")
                elif isinstance(tool_input, str):
                    query_text = tool_input
                active_delegations[run_id] = {"slug": slug, "query": query_text}
                yield {"type": "agent_start", "run_id": run_id, "slug": slug, "query": query_text}

            elif kind == "on_tool_start" and name in _PRES_TOOLS:
                tool_input = event.get("data", {}).get("input", {})
                pid = tool_input.get("presentation_id", "") if isinstance(tool_input, dict) else ""
                if pid:
                    pending_pres_ids[run_id] = pid
                yield {"type": "tool_call_start", "run_id": run_id, "tool_name": name, "args": (tool_input if isinstance(tool_input, dict) else {})}

            elif kind == "on_tool_start":
                tool_input = event.get("data", {}).get("input", {})
                yield {"type": "tool_call_start", "run_id": run_id, "tool_name": name, "args": (tool_input if isinstance(tool_input, dict) else {})}

            elif kind == "on_tool_end" and name.startswith(DELEGATION_PREFIX):
                info = active_delegations.pop(run_id, None)
                if info:
                    yield {"type": "agent_done", "run_id": run_id}
                if collected:
                    pending_separator = True

            elif kind == "on_tool_end" and name in _PRES_TOOLS:
                tool_output = str(event.get("data", {}).get("output", ""))
                pres_id = None
                if "ID:" in tool_output:
                    pres_id = tool_output.split("ID:")[1].strip().split()[0]
                if not pres_id:
                    pres_id = pending_pres_ids.pop(run_id, None)
                if pres_id and not tool_output.startswith("Error:"):
                    yield {"type": "presentation_update", "presentation_id": pres_id}
                yield {"type": "tool_call_end", "run_id": run_id, "tool_name": name, "result": tool_output[:2000]}
                if collected:
                    pending_separator = True

            elif kind == "on_tool_end" and name in _TASK_TOOLS:
                tool_output = str(event.get("data", {}).get("output", ""))
                yield {"type": "task_update", "session_id": str(session_id)}
                yield {"type": "tool_call_end", "run_id": run_id, "tool_name": name, "result": tool_output[:2000]}
                if collected:
                    pending_separator = True

            elif kind == "on_tool_end":
                tool_output = str(event.get("data", {}).get("output", ""))
                yield {"type": "tool_call_end", "run_id": run_id, "tool_name": name, "result": tool_output[:2000]}
                if collected:
                    pending_separator = True

            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = getattr(chunk, "content", "")

                thinking_text = ""
                text_content = ""

                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "thinking":
                                thinking_text += block.get("thinking", "")
                            else:
                                text_content += block.get("text", "")
                        elif isinstance(block, str):
                            text_content += block
                elif isinstance(content, str):
                    text_content = content

                if not thinking_text and not text_content:
                    continue

                child_run = next(
                    (pid for pid in parent_ids if pid in active_delegations),
                    None,
                )

                if thinking_text:
                    if child_run:
                        yield {"type": "agent_token", "run_id": child_run, "content": thinking_text}
                    else:
                        yield {"type": "thinking", "content": thinking_text}

                if text_content:
                    if child_run:
                        yield {"type": "agent_token", "run_id": child_run, "content": text_content}
                    else:
                        if pending_separator:
                            collected += "\n\n"
                            yield {"type": "token", "content": "\n\n"}
                            pending_separator = False
                        collected += text_content
                        yield {"type": "token", "content": text_content}

    try:
        async for ev in _consume_stream(attempt=1):
            yield ev
    except Exception as exc:
        err_str = str(exc).lower()
        is_prompt_too_long = ("prompt" in err_str or "context" in err_str) and (
            "long" in err_str or "token" in err_str or "length" in err_str or "exceed" in err_str
        )
        if is_prompt_too_long:
            logger.warning("Prompt too long -- attempting emergency compaction and retry")
            emergency_llm = build_llm_from_provider(provider, streaming=False)
            await cleanup_checkpoint(
                agent, run_config, emergency_llm, agent_config, provider, force=True,
            )
            try:
                async for ev in _consume_stream(attempt=2):
                    yield ev
            except Exception:
                logger.exception("Retry after emergency compaction also failed")
        else:
            logger.exception("Unhandled error during agent streaming")

    if not collected:
        try:
            snapshot = await agent.aget_state(run_config)
            if snapshot and snapshot.values:
                msgs = snapshot.values.get("messages", [])
                if msgs:
                    last_msg = msgs[-1]
                    raw = getattr(last_msg, "content", "")
                    if isinstance(raw, list):
                        raw = "".join(
                            c.get("text", "") if isinstance(c, dict) else str(c)
                            for c in raw
                        )
                    if raw:
                        collected = raw
                        yield {"type": "token", "content": collected}
        except Exception:
            logger.debug("Could not read checkpoint state for fallback")

        if not collected:
            collected = "I wasn't able to generate a response."
            yield {"type": "token", "content": collected}

    llm = build_llm_from_provider(provider, streaming=False)

    if session_id:
        try:
            post_snapshot = await agent.aget_state(run_config)
            post_msgs = post_snapshot.values.get("messages", []) if post_snapshot and post_snapshot.values else []
            updated_notes = await maybe_update_session_notes(
                session_id, post_msgs, existing_notes, notes_cursor, llm,
            )
            if updated_notes:
                await agent.aupdate_state(run_config, {"session_notes": updated_notes})
        except Exception:
            logger.debug("Session notes update failed (non-critical)", exc_info=True)

    await cleanup_checkpoint(agent, run_config, llm, agent_config, provider)

    if user_id and collected and mem_settings.memory_enabled and mem_settings.extraction_enabled:
        turn_msgs = [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": collected},
        ]
        asyncio.create_task(extract_memories(user_id, turn_msgs))
        asyncio.create_task(maybe_consolidate(user_id, llm))
