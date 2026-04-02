"""Skill loading and seeding for the agent prompt extension system."""

from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_skill import AgentSkill

logger = logging.getLogger(__name__)


async def load_active_skills(agent_slug: str, db: AsyncSession) -> str:
    """Load auto-inject skills matching *agent_slug* and return formatted prompt sections."""
    result = await db.scalars(
        select(AgentSkill).where(
            AgentSkill.is_active.is_(True),
            AgentSkill.auto_inject.is_(True),
            or_(
                AgentSkill.applicable_agents.is_(None),
                AgentSkill.applicable_agents.contains([agent_slug]),
            ),
        )
    )
    skills = result.all()
    if not skills:
        return ""
    sections = [f"## Skill: {s.name}\n{s.prompt_content}" for s in skills]
    return "\n\n---\n\n".join(sections)


async def list_available_skills(agent_slug: str, db: AsyncSession) -> list[dict]:
    """Return non-auto-inject skills available to an agent (for the use_skill tool)."""
    result = await db.scalars(
        select(AgentSkill).where(
            AgentSkill.is_active.is_(True),
            AgentSkill.auto_inject.is_(False),
            or_(
                AgentSkill.applicable_agents.is_(None),
                AgentSkill.applicable_agents.contains([agent_slug]),
            ),
        )
    )
    return [
        {"slug": s.slug, "name": s.name, "description": s.description or ""}
        for s in result.all()
    ]


BUILTIN_SKILLS: list[dict] = [
    {
        "slug": "data-exploration-workflow",
        "name": "Data Exploration Workflow",
        "description": "Systematic approach to discovering and validating data before building visualizations",
        "applicable_agents": None,  # available to all agents
        "auto_inject": False,
        "prompt_content": """\
Systematic data exploration workflow. Follow these steps BEFORE writing any component code.

### Step 1: Schema Discovery
List available tables and describe each relevant one. Record exact column names
and types -- you will need them for queries.

### Step 2: Sample Data
For each relevant table, run sample queries with LIMIT 5 to see actual data
shapes. Pay attention to:
- NULL frequency in important columns
- Date formats and ranges
- Enum values (states, statuses, types)
- Foreign key patterns

### Step 3: Aggregation Probes
Run aggregate queries to understand data volume and distribution:
- `COUNT(*)` per table
- `MIN/MAX` on date columns (to know the time range)
- `COUNT(DISTINCT ...)` on key dimensions
- `GROUP BY` on categorical columns to see cardinality

### Step 4: Anomaly Check
Before building charts, verify the data makes sense:
- Are there gaps in time series? (missing days/sprints)
- Are there outliers that would skew averages?
- Is there enough data for meaningful trends? (< 3 data points = warn user)

### Step 5: Query Plan
Document the exact queries you will use:
- Write the SQL and test it
- Confirm column names match the schema (NEVER guess)
- Verify result shapes match what your charts expect""",
    },
]


async def seed_builtin_skills(db: AsyncSession) -> None:
    """Upsert builtin skills. Existing skills get their prompt_content updated."""
    changed = False
    for spec in BUILTIN_SKILLS:
        result = await db.execute(
            select(AgentSkill).where(AgentSkill.slug == spec["slug"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            db.add(AgentSkill(
                slug=spec["slug"],
                name=spec["name"],
                description=spec.get("description"),
                prompt_content=spec["prompt_content"],
                applicable_agents=spec.get("applicable_agents"),
                auto_inject=spec.get("auto_inject", False),
                is_active=True,
            ))
            changed = True
            logger.info("Seeded builtin skill: %s", spec["slug"])
        elif existing.prompt_content != spec["prompt_content"]:
            existing.prompt_content = spec["prompt_content"]
            existing.name = spec["name"]
            existing.description = spec.get("description")
            changed = True
            logger.info("Updated builtin skill: %s", spec["slug"])
    if changed:
        await db.commit()
