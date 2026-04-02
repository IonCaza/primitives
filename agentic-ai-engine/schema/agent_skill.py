"""Agent skills: injectable prompt fragments with per-agent targeting."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentSkill(Base):
    __tablename__ = "agent_skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_content: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Markdown prompt injected into the agent system prompt",
    )
    applicable_agents: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)), nullable=True,
        comment="Agent slugs this skill targets; NULL = all agents",
    )
    auto_inject: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="If True, injected automatically into matching agents' prompts",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
