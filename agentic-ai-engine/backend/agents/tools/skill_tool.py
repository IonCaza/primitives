"""On-demand skill activation tool.

Agents call this to load a skill's prompt into their current context.
Only non-auto-inject skills are available (auto-inject skills are already
in the system prompt).
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool
from sqlalchemy import select

from app.agents.tools.base import ToolDefinition
from app.agents.tools.registry import register_tool_category
from app.db.base import async_session
from app.db.models.agent_skill import AgentSkill

logger = logging.getLogger(__name__)

CATEGORY = "skills"

DEFINITIONS = [
    ToolDefinition(
        slug="use_skill",
        name="use_skill",
        description="Load a skill's specialized instructions into the current context.",
        category=CATEGORY,
        concurrency_safe=True,
    ),
    ToolDefinition(
        slug="list_skills",
        name="list_skills",
        description="List available skills you can activate.",
        category=CATEGORY,
        concurrency_safe=True,
    ),
]


def _build_skill_tools(db):
    @tool
    async def use_skill(skill_slug: str) -> str:
        """Load a skill's specialized instructions for the current task.

        Skills provide domain-specific guidance like layout patterns,
        data exploration workflows, or chart selection criteria.
        Call list_skills first to see what's available.
        """
        async with async_session() as session:
            result = await session.scalar(
                select(AgentSkill).where(
                    AgentSkill.slug == skill_slug,
                    AgentSkill.is_active.is_(True),
                )
            )
        if not result:
            return f"Skill '{skill_slug}' not found or inactive"
        return f"## Active Skill: {result.name}\n\n{result.prompt_content}"

    @tool
    async def list_skills() -> str:
        """List available skills you can activate with use_skill."""
        async with async_session() as session:
            results = await session.scalars(
                select(AgentSkill).where(
                    AgentSkill.is_active.is_(True),
                    AgentSkill.auto_inject.is_(False),
                )
            )
        skills = results.all()
        if not skills:
            return "No skills available."
        lines = [f"- **{s.slug}**: {s.name} — {s.description or 'No description'}" for s in skills]
        return "Available skills:\n" + "\n".join(lines)

    return [use_skill, list_skills]


register_tool_category(CATEGORY, DEFINITIONS, _build_skill_tools, session_safe=True, concurrency_safe=True)
