from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.auth.dependencies import get_current_user
from app.db.base import get_db
from app.db.models.chat import ChatSession, ChatMessage, MessageRole
from app.db.models.agent_activity import AgentActivity
from app.db.models.console_entry import ConsoleEntry
from app.db.models.ai_settings import AiSettings, SINGLETON_ID
from app.db.models.agent_config import AgentConfig
from app.db.models.task_item import TaskItem
from app.db.models.user import User
from app.agents.runner import run_agent_stream, resume_agent_stream

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class AttachmentContent(BaseModel):
    type: str
    data: str
    name: str = "attachment"


class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str
    agent_slug: str = "supervisor"
    attachments: list[AttachmentContent] | None = None


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    title: str
    agent_slug: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentActivityOut(BaseModel):
    id: uuid.UUID
    trigger_message_id: uuid.UUID
    agent_slug: str
    run_id: str
    delegation_query: str = ""
    content: str
    started_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConsoleEntryOut(BaseModel):
    id: uuid.UUID
    entry_type: str
    sequence: int = 0
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: str | None = None
    thinking_content: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    agent_activities: list[AgentActivityOut] = []
    console_entries: list[ConsoleEntryOut] = []

    model_config = {"from_attributes": True}


async def _persist_response(
    db: AsyncSession,
    session_id: uuid.UUID,
    content: str,
    trigger_message_id: uuid.UUID | None = None,
    agent_activities: list[dict] | None = None,
    console_entries: list[dict] | None = None,
) -> None:
    """Save the assistant response, any agent activities, console entries, and update the session.

    Retries once after rollback in case the session was poisoned by a
    prior failed transaction.
    """
    for attempt in range(2):
        try:
            if attempt > 0:
                await db.rollback()

            assistant_msg = ChatMessage(
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=content,
            )
            db.add(assistant_msg)
            await db.flush()

            if trigger_message_id and agent_activities:
                for act in agent_activities:
                    db.add(AgentActivity(
                        session_id=session_id,
                        trigger_message_id=trigger_message_id,
                        response_message_id=assistant_msg.id,
                        agent_slug=act["slug"],
                        run_id=act["run_id"],
                        delegation_query=act.get("delegation_query", ""),
                        content=act["content"],
                        started_at=act["started_at"],
                        finished_at=act.get("finished_at"),
                    ))

            if console_entries:
                try:
                    async with db.begin_nested():
                        for idx, ce in enumerate(console_entries):
                            db.add(ConsoleEntry(
                                session_id=session_id,
                                message_id=assistant_msg.id,
                                entry_type=ce["entry_type"],
                                sequence=idx,
                                tool_name=ce.get("tool_name"),
                                tool_args=ce.get("tool_args"),
                                tool_result=ce.get("tool_result"),
                                thinking_content=ce.get("thinking_content"),
                                started_at=ce["started_at"],
                                finished_at=ce.get("finished_at"),
                            ))
                except Exception:
                    logger.warning("Failed to persist console entries (non-fatal)")

            await db.execute(
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(updated_at=datetime.now(timezone.utc))
            )
            await db.commit()
            return
        except Exception:
            if attempt == 0:
                logger.warning("Session may be poisoned, retrying after rollback")
            else:
                raise


@router.post("")
async def send_message(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ai_row = (await db.execute(select(AiSettings).where(AiSettings.id == SINGLETON_ID))).scalar_one_or_none()
    if not (ai_row and ai_row.enabled):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI is not enabled. An admin must enable it in Settings > AI.",
        )

    agent_row = (await db.execute(
        select(AgentConfig).where(AgentConfig.slug == body.agent_slug, AgentConfig.enabled.is_(True))
    )).scalar_one_or_none()
    if not agent_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{body.agent_slug}' not found or not enabled.",
        )

    try:
        if body.session_id:
            result = await db.execute(
                select(ChatSession).where(
                    ChatSession.id == body.session_id,
                    ChatSession.user_id == user.id,
                )
            )
            session = result.scalar_one_or_none()
            if not session:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
            if session.title == "New chat":
                session.title = body.message[:100].strip() or "New chat"
        else:
            title = body.message[:100].strip() or "New chat"
            session = ChatSession(user_id=user.id, title=title, agent_id=agent_row.id)
            db.add(session)
            await db.flush()

        user_msg = ChatMessage(
            session_id=session.id,
            role=MessageRole.USER,
            content=body.message,
        )
        db.add(user_msg)
        await db.flush()
        session_id = session.id
        trigger_message_id = user_msg.id
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to persist chat message")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process chat message.",
        )

    async def event_generator():
        collected = ""
        activities: dict[str, dict] = {}
        console_log: list[dict] = []
        thinking_acc = ""
        try:
            yield {"event": "session", "data": json.dumps({"session_id": str(session_id)})}
            async for evt in run_agent_stream(
                db, body.message,
                agent_slug=body.agent_slug,
                session_id=session_id,
                user_id=user.id,
                attachments=[a.model_dump() for a in body.attachments] if body.attachments else None,
            ):
                etype = evt["type"]
                if etype == "token":
                    collected += evt["content"]
                    yield {"event": "token", "data": json.dumps({"content": evt["content"]})}
                elif etype == "thinking":
                    thinking_acc += evt["content"]
                    yield {"event": "thinking", "data": json.dumps({"content": evt["content"]})}
                elif etype == "agent_start":
                    activities[evt["run_id"]] = {
                        "slug": evt["slug"],
                        "run_id": evt["run_id"],
                        "delegation_query": evt.get("query", ""),
                        "content": "",
                        "started_at": datetime.now(timezone.utc),
                        "finished_at": None,
                    }
                    yield {"event": "agent_start", "data": json.dumps({"run_id": evt["run_id"], "slug": evt["slug"], "query": evt.get("query", "")})}
                elif etype == "agent_token":
                    act = activities.get(evt["run_id"])
                    if act:
                        act["content"] += evt["content"]
                    yield {"event": "agent_token", "data": json.dumps({"run_id": evt["run_id"], "content": evt["content"]})}
                elif etype == "agent_done":
                    act = activities.get(evt["run_id"])
                    if act:
                        act["finished_at"] = datetime.now(timezone.utc)
                    yield {"event": "agent_done", "data": json.dumps({"run_id": evt["run_id"]})}
                elif etype == "tool_call_start":
                    console_log.append({
                        "run_id": evt["run_id"],
                        "entry_type": "tool_call",
                        "tool_name": evt.get("tool_name"),
                        "tool_args": evt.get("args"),
                        "started_at": datetime.now(timezone.utc),
                    })
                    yield {"event": "tool_call_start", "data": json.dumps({"run_id": evt["run_id"], "tool_name": evt.get("tool_name"), "args": evt.get("args")})}
                elif etype == "tool_call_end":
                    for ce in reversed(console_log):
                        if ce.get("run_id") == evt["run_id"] and ce["entry_type"] == "tool_call" and not ce.get("finished_at"):
                            ce["tool_result"] = evt.get("result")
                            ce["finished_at"] = datetime.now(timezone.utc)
                            break
                    yield {"event": "tool_call_end", "data": json.dumps({"run_id": evt["run_id"], "tool_name": evt.get("tool_name"), "result": evt.get("result")})}
                elif etype == "presentation_update":
                    yield {"event": "presentation_update", "data": json.dumps({"presentation_id": evt["presentation_id"]})}
                elif etype == "task_update":
                    yield {"event": "task_update", "data": json.dumps({"session_id": evt["session_id"]})}
                elif etype == "error":
                    collected = evt.get("content", "Access denied.")
                    yield {"event": "error", "data": json.dumps({"detail": collected})}
                elif etype == "client_tool_request":
                    yield {
                        "event": "client_tool_request",
                        "data": json.dumps({
                            "call_id": evt.get("call_id", ""),
                            "tool_name": evt.get("tool_name", ""),
                            "args": evt.get("args", {}),
                            "thread_id": evt.get("thread_id", ""),
                            "session_id": str(session_id),
                            "agent_slug": body.agent_slug,
                        }),
                    }
                    return

            if thinking_acc:
                console_log.append({
                    "entry_type": "thinking",
                    "thinking_content": thinking_acc,
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": datetime.now(timezone.utc),
                })

            yield {"event": "done", "data": json.dumps({"content": collected})}
        except Exception as exc:
            logger.exception("Agent streaming error")
            if not collected:
                exc_str = str(exc).lower()
                if "rate" in exc_str and "limit" in exc_str:
                    collected = (
                        "The AI provider is temporarily rate-limited. "
                        "Please wait a moment and try again."
                    )
                else:
                    collected = "Sorry, I encountered an error processing your request."
                yield {"event": "error", "data": json.dumps({"detail": collected})}
        finally:
            content = collected or "No response generated."
            activity_list = list(activities.values()) if activities else None
            console_list = [ce for ce in console_log if "run_id" not in ce or ce.get("entry_type")] or None
            try:
                await asyncio.shield(
                    _persist_response(
                        db, session_id, content,
                        trigger_message_id=trigger_message_id,
                        agent_activities=activity_list,
                        console_entries=console_list,
                    )
                )
            except asyncio.CancelledError:
                logger.debug("SSE cancelled during persist — shielded task still running")
            except Exception:
                logger.exception("Failed to persist assistant response")

    return EventSourceResponse(event_generator())


class ClientToolResult(BaseModel):
    thread_id: str
    session_id: uuid.UUID
    agent_slug: str = "supervisor"
    call_id: str
    result: str


@router.post("/tool-result")
async def submit_tool_result(
    body: ClientToolResult,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a client-side tool result and resume the interrupted agent graph.

    The frontend calls this after executing the tool locally, providing the
    result. A new SSE stream is returned that continues from the interrupted
    checkpoint.
    """

    async def event_generator():
        collected = ""
        activities: dict[str, dict] = {}
        console_log: list[dict] = []
        thinking_acc = ""
        try:
            async for evt in resume_agent_stream(
                db,
                body.thread_id,
                body.result,
                agent_slug=body.agent_slug,
                session_id=body.session_id,
                user_id=user.id,
            ):
                etype = evt["type"]
                if etype == "token":
                    collected += evt["content"]
                    yield {"event": "token", "data": json.dumps({"content": evt["content"]})}
                elif etype == "thinking":
                    thinking_acc += evt["content"]
                    yield {"event": "thinking", "data": json.dumps({"content": evt["content"]})}
                elif etype == "agent_start":
                    activities[evt["run_id"]] = {
                        "slug": evt["slug"],
                        "run_id": evt["run_id"],
                        "delegation_query": evt.get("query", ""),
                        "content": "",
                        "started_at": datetime.now(timezone.utc),
                        "finished_at": None,
                    }
                    yield {"event": "agent_start", "data": json.dumps({"run_id": evt["run_id"], "slug": evt["slug"], "query": evt.get("query", "")})}
                elif etype == "agent_token":
                    act = activities.get(evt["run_id"])
                    if act:
                        act["content"] += evt["content"]
                    yield {"event": "agent_token", "data": json.dumps({"run_id": evt["run_id"], "content": evt["content"]})}
                elif etype == "agent_done":
                    act = activities.get(evt["run_id"])
                    if act:
                        act["finished_at"] = datetime.now(timezone.utc)
                    yield {"event": "agent_done", "data": json.dumps({"run_id": evt["run_id"]})}
                elif etype == "tool_call_start":
                    console_log.append({
                        "run_id": evt["run_id"],
                        "entry_type": "tool_call",
                        "tool_name": evt.get("tool_name"),
                        "tool_args": evt.get("args"),
                        "started_at": datetime.now(timezone.utc),
                    })
                    yield {"event": "tool_call_start", "data": json.dumps({"run_id": evt["run_id"], "tool_name": evt.get("tool_name"), "args": evt.get("args")})}
                elif etype == "tool_call_end":
                    for ce in reversed(console_log):
                        if ce.get("run_id") == evt["run_id"] and ce["entry_type"] == "tool_call" and not ce.get("finished_at"):
                            ce["tool_result"] = evt.get("result")
                            ce["finished_at"] = datetime.now(timezone.utc)
                            break
                    yield {"event": "tool_call_end", "data": json.dumps({"run_id": evt["run_id"], "tool_name": evt.get("tool_name"), "result": evt.get("result")})}
                elif etype == "presentation_update":
                    yield {"event": "presentation_update", "data": json.dumps({"presentation_id": evt["presentation_id"]})}
                elif etype == "task_update":
                    yield {"event": "task_update", "data": json.dumps({"session_id": evt["session_id"]})}
                elif etype == "client_tool_request":
                    yield {"event": "client_tool_request", "data": json.dumps({
                        "call_id": evt.get("call_id", ""),
                        "tool_name": evt.get("tool_name", ""),
                        "args": evt.get("args", {}),
                        "thread_id": evt.get("thread_id", ""),
                        "session_id": str(body.session_id),
                        "agent_slug": body.agent_slug,
                    })}
                    return
                elif etype == "error":
                    collected = evt.get("content", "An error occurred.")
                    yield {"event": "error", "data": json.dumps({"detail": collected})}

            if thinking_acc:
                console_log.append({
                    "entry_type": "thinking",
                    "thinking_content": thinking_acc,
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": datetime.now(timezone.utc),
                })

            yield {"event": "done", "data": json.dumps({"resumed": True})}
        except Exception:
            logger.exception("Error during tool-result resume")
            if not collected:
                collected = "Sorry, I encountered an error processing your request."
            yield {"event": "error", "data": json.dumps({"detail": "Resume failed"})}
        finally:
            if collected:
                content = collected
                activity_list = list(activities.values()) if activities else None
                console_list = [ce for ce in console_log if "run_id" not in ce or ce.get("entry_type")] or None
                try:
                    await asyncio.shield(
                        _persist_response(
                            db, body.session_id, content,
                            agent_activities=activity_list,
                            console_entries=console_list,
                        )
                    )
                except asyncio.CancelledError:
                    logger.debug("SSE cancelled during resume persist — shielded task still running")
                except Exception:
                    logger.exception("Failed to persist resume response")

    return EventSourceResponse(event_generator())


class RenameRequest(BaseModel):
    title: str


def _session_out(s: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(
        id=s.id,
        title=s.title,
        agent_slug=None,
        archived_at=s.archived_at,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = ChatSession(user_id=user.id, title="New chat")
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _session_out(session)


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def rename_session(
    session_id: uuid.UUID,
    body: RenameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.title = body.title
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return _session_out(session)


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()
    return [_session_out(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=list[ChatMessageOut])
async def get_session_messages(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    msgs = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = msgs.scalars().all()

    acts_result = await db.execute(
        select(AgentActivity)
        .where(AgentActivity.session_id == session_id)
        .order_by(AgentActivity.started_at)
    )
    activities = acts_result.scalars().all()

    acts_by_response: dict[uuid.UUID, list[AgentActivity]] = {}
    for act in activities:
        acts_by_response.setdefault(act.response_message_id, []).append(act)

    ce_result = await db.execute(
        select(ConsoleEntry)
        .where(ConsoleEntry.session_id == session_id)
        .order_by(ConsoleEntry.sequence)
    )
    console_entries = ce_result.scalars().all()

    ce_by_message: dict[uuid.UUID, list[ConsoleEntry]] = {}
    for ce in console_entries:
        ce_by_message.setdefault(ce.message_id, []).append(ce)

    out: list[ChatMessageOut] = []
    for msg in messages:
        msg_acts = acts_by_response.get(msg.id, [])
        msg_ces = ce_by_message.get(msg.id, [])
        out.append(ChatMessageOut(
            id=msg.id,
            role=msg.role.value if hasattr(msg.role, "value") else msg.role,
            content=msg.content,
            created_at=msg.created_at,
            agent_activities=[AgentActivityOut.model_validate(a) for a in msg_acts],
            console_entries=[ConsoleEntryOut.model_validate(ce) for ce in msg_ces],
        ))
    return out


@router.post("/sessions/{session_id}/archive", response_model=ChatSessionOut)
async def archive_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.archived_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return _session_out(session)


@router.post("/sessions/{session_id}/unarchive", response_model=ChatSessionOut)
async def unarchive_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.archived_at = None
    await db.commit()
    await db.refresh(session)
    return _session_out(session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await db.delete(session)
    await db.commit()


class TaskItemOut(BaseModel):
    id: str
    subject: str
    description: str | None = None
    status: str
    owner_agent_slug: str | None = None
    blocked_by: list[str] = []
    blocks: list[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/sessions/{session_id}/tasks", response_model=list[TaskItemOut])
async def get_session_tasks(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sess = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id)
    )).scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    tasks = (await db.scalars(
        select(TaskItem).where(TaskItem.session_id == session_id).order_by(TaskItem.id)
    )).all()
    return [TaskItemOut.model_validate(t) for t in tasks]
