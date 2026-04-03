"""Structured task decomposition tools for agent work planning.

Agents use these tools to break complex requests into discrete, trackable
tasks with dependencies.  Tasks are persisted per chat session and surfaced
to the frontend via SSE events.

Each tool opens its own database session to avoid conflicts with
LangGraph's checkpoint session (which may be mid-flush when tools execute).

Registered as category ``task_management`` (session-safe).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import ToolDefinition
from app.agents.tools.registry import register_tool_category
from app.db.base import async_session

logger = logging.getLogger(__name__)

DEFINITIONS = [
    ToolDefinition(slug="create_task", name="create_task", description="Create a new task for the current session", category="task_management"),
    ToolDefinition(slug="update_task", name="update_task", description="Update a task's status, ownership, or dependencies", category="task_management"),
    ToolDefinition(slug="list_tasks", name="list_tasks", description="List all tasks for the current session grouped by status", category="task_management", concurrency_safe=True),
    ToolDefinition(slug="get_task", name="get_task", description="Get full details for a single task", category="task_management", concurrency_safe=True),
]

_VERIFY_KEYWORDS = re.compile(r"verif|check|review|confirm|validate", re.IGNORECASE)
_VALID_STATUSES = {"pending", "in_progress", "completed", "blocked", "cancelled"}


def _build_task_tools(*, session_id: uuid.UUID) -> list:
    """Build task management tools scoped to a chat session."""
    from app.db.models.task_item import TaskItem

    @tool
    async def create_task(
        subject: str,
        description: str = "",
        blocked_by: Optional[list[str]] = None,
        owner_agent_slug: Optional[str] = None,
    ) -> str:
        """Create a new task for the current work plan.

        Use this to decompose a complex request into discrete steps before
        starting implementation.  Each task should be specific enough that
        a single agent can complete it without guessing your intent.

        Args:
            subject: Short title (max 200 chars) describing what needs to be done.
            description: Longer explanation with specifics -- exact table names,
                         column names, query shapes, expected outputs.
            blocked_by: List of task IDs (e.g. ["t1", "t2"]) that must complete
                        before this task can start.
            owner_agent_slug: Optional agent slug to assign this task to.
        """
        blocked_by = blocked_by or []

        async with async_session() as db:
            lock_key = hash(str(session_id)) % (2**31 - 1)
            await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

            count = await db.scalar(
                select(func.count(TaskItem.id)).where(TaskItem.session_id == session_id)
            )
            next_num = (count or 0) + 1
            task_id = f"t{next_num}"

            if blocked_by:
                existing = set((await db.scalars(
                    select(TaskItem.id).where(
                        TaskItem.session_id == session_id,
                        TaskItem.id.in_(blocked_by),
                    )
                )).all())
                missing = set(blocked_by) - existing
                if missing:
                    logger.debug(
                        "create_task: blocked_by refs %s not yet in DB "
                        "(likely forward-references in a parallel batch)",
                        missing,
                    )

            task = TaskItem(
                id=task_id,
                session_id=session_id,
                subject=subject[:200],
                description=description or None,
                status="pending",
                owner_agent_slug=owner_agent_slug,
                blocked_by=blocked_by,
                blocks=[],
            )
            db.add(task)

            if blocked_by:
                blockers = (await db.scalars(
                    select(TaskItem).where(
                        TaskItem.session_id == session_id,
                        TaskItem.id.in_(blocked_by),
                    )
                )).all()
                for blocker in blockers:
                    current_blocks = list(blocker.blocks or [])
                    if task_id not in current_blocks:
                        current_blocks.append(task_id)
                        blocker.blocks = current_blocks

            await db.commit()

        return (
            f"Task {task_id} created: \"{subject}\""
            + (f" (blocked by: {', '.join(blocked_by)})" if blocked_by else "")
        )

    @tool
    async def update_task(
        task_id: str,
        status: Optional[str] = None,
        owner_agent_slug: Optional[str] = None,
        description: Optional[str] = None,
    ) -> str:
        """Update a task's status, ownership, or description.

        Args:
            task_id: The task ID to update (e.g. "t1").
            status: New status -- one of: pending, in_progress, completed,
                    blocked, cancelled.
            owner_agent_slug: Reassign ownership to a different agent.
            description: Replace the task description with new details.
        """
        async with async_session() as db:
            task = (await db.scalars(
                select(TaskItem).where(TaskItem.id == task_id, TaskItem.session_id == session_id)
            )).first()
            if not task:
                return f"Error: task '{task_id}' not found in this session."

            if status:
                if status not in _VALID_STATUSES:
                    return f"Error: invalid status '{status}'. Use one of: {', '.join(sorted(_VALID_STATUSES))}"
                task.status = status

            if owner_agent_slug is not None:
                task.owner_agent_slug = owner_agent_slug

            if description is not None:
                task.description = description

            await db.commit()

        parts = [f"Task {task_id} updated"]
        if status:
            parts.append(f"status={status}")
        if owner_agent_slug is not None:
            parts.append(f"owner={owner_agent_slug}")
        result = " | ".join(parts) + "."

        if status == "completed":
            nudge = await _verification_nudge(session_id)
            if nudge:
                result += "\n\n" + nudge

        return result

    @tool
    async def list_tasks() -> str:
        """List all tasks for the current session, grouped by status.

        Use this to review the current work plan and decide what to tackle next.
        Prefer working on tasks with the lowest ID first -- earlier tasks often
        establish context that later ones depend on.
        """
        async with async_session() as db:
            tasks = (await db.scalars(
                select(TaskItem)
                .where(TaskItem.session_id == session_id)
                .order_by(TaskItem.id)
            )).all()

            if not tasks:
                return "No tasks created yet. Use create_task to break down the current request into steps."

            blocker_ids = {bid for t in tasks for bid in (t.blocked_by or [])}
            blocker_map: dict[str, TaskItem] = {}
            if blocker_ids:
                blockers = (await db.scalars(
                    select(TaskItem).where(
                        TaskItem.session_id == session_id,
                        TaskItem.id.in_(blocker_ids),
                    )
                )).all()
                blocker_map = {b.id: b for b in blockers}

            groups: dict[str, list[str]] = {}
            for t in tasks:
                incomplete_blockers = []
                for bid in (t.blocked_by or []):
                    blocker = blocker_map.get(bid)
                    if blocker and blocker.status != "completed":
                        incomplete_blockers.append(bid)

                line = f"  {t.id}: {t.subject}"
                if incomplete_blockers:
                    line += f"  (blocked by: {', '.join(incomplete_blockers)})"
                if t.owner_agent_slug:
                    line += f"  [owner: {t.owner_agent_slug}]"
                groups.setdefault(t.status, []).append(line)

            total = len(tasks)
            done = sum(1 for t in tasks if t.status == "completed")

        sections = []
        for status_label in ["in_progress", "pending", "blocked", "completed", "cancelled"]:
            items = groups.get(status_label, [])
            if items:
                sections.append(f"### {status_label} ({len(items)})\n" + "\n".join(items))

        header = f"Tasks: {done}/{total} completed"
        return header + "\n\n" + "\n\n".join(sections)

    @tool
    async def get_task(task_id: str) -> str:
        """Get full details for a specific task including its dependency chain.

        Args:
            task_id: The task ID to look up (e.g. "t1").
        """
        async with async_session() as db:
            task = (await db.scalars(
                select(TaskItem).where(TaskItem.id == task_id, TaskItem.session_id == session_id)
            )).first()
            if not task:
                return f"Error: task '{task_id}' not found in this session."

            lines = [
                f"**{task.id}: {task.subject}**",
                f"Status: {task.status}",
            ]
            if task.description:
                lines.append(f"Description: {task.description}")
            if task.owner_agent_slug:
                lines.append(f"Owner: {task.owner_agent_slug}")
            if task.blocked_by:
                blockers = (await db.scalars(
                    select(TaskItem).where(
                        TaskItem.session_id == session_id,
                        TaskItem.id.in_(task.blocked_by),
                    )
                )).all()
                blocker_by_id = {b.id: b for b in blockers}
                blocker_details = []
                for bid in task.blocked_by:
                    b = blocker_by_id.get(bid)
                    if b:
                        marker = "done" if b.status == "completed" else b.status
                        blocker_details.append(f"{bid} ({marker})")
                    else:
                        blocker_details.append(f"{bid} (missing)")
                lines.append(f"Blocked by: {', '.join(blocker_details)}")
            if task.blocks:
                lines.append(f"Blocks: {', '.join(task.blocks)}")

        return "\n".join(lines)

    return [create_task, update_task, list_tasks, get_task]


async def _verification_nudge(session_id: uuid.UUID) -> str | None:
    """Return a verification nudge if all 3+ tasks are done and none is a check."""
    from app.db.models.task_item import TaskItem

    async with async_session() as db:
        tasks = (await db.scalars(
            select(TaskItem).where(TaskItem.session_id == session_id)
        )).all()

    if len(tasks) < 3:
        return None

    all_done = all(t.status == "completed" for t in tasks)
    if not all_done:
        return None

    has_verify = any(_VERIFY_KEYWORDS.search(t.subject) for t in tasks)
    if has_verify:
        return None

    return (
        "All planned work is marked done. Strongly consider running a "
        "verification pass -- assign a fresh agent to independently confirm "
        "the key outputs before reporting to the user."
    )


def build_task_tools(db: AsyncSession, session_id: uuid.UUID) -> list:
    """Public entry point used by the runner to inject task tools.

    The ``db`` parameter is accepted for API compatibility but not used --
    task tools open their own sessions to avoid conflicts with LangGraph's
    checkpoint session.
    """
    return _build_task_tools(session_id=session_id)


def _factory(db: AsyncSession) -> list:
    """Registry-compatible factory. Returns empty since task tools need session_id.

    Actual tool instances are built by ``build_task_tools()`` in the runner
    and injected via ``extra_tools``.
    """
    return []


register_tool_category(
    "task_management",
    DEFINITIONS,
    _factory,
    session_safe=True,
)
