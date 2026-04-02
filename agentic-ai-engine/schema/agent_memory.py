"""Structured long-term memory with 4-type taxonomy."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    agent_slug: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="NULL = shared across agents",
    )
    name: Mapped[str] = mapped_column(
        String(200), nullable=False,
        comment="Short identifier (e.g. revenue-metric-preference)",
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="One-line summary used for relevance ranking during recall",
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="user | feedback | project | reference",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('user', 'feedback', 'project', 'reference')",
            name="ck_agent_memories_type",
        ),
        Index("ix_agent_memories_user_id", "user_id"),
        Index("ix_agent_memories_user_type", "user_id", "type"),
    )
