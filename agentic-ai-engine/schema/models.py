"""Canonical SQLAlchemy model definitions for the Agentic AI Engine.

These are reference models. Adapt import paths and Base class to match
your project's ORM setup. See INTEGRATION.md Section 1.1 for details.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# --- ADAPT THIS IMPORT to your project's declarative base ---
from app.db.base import Base


# ---------------------------------------------------------------------------
# AI Settings (singleton)
# ---------------------------------------------------------------------------

SINGLETON_ID = 1


class AiSettings(Base):
    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    extraction_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    extraction_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True
    )
    extraction_enable_inserts: Mapped[bool] = mapped_column(Boolean, default=True)
    extraction_enable_updates: Mapped[bool] = mapped_column(Boolean, default=True)
    extraction_enable_deletes: Mapped[bool] = mapped_column(Boolean, default=False)
    cleanup_threshold_ratio: Mapped[float] = mapped_column(Float, default=0.6)
    summary_token_ratio: Mapped[float] = mapped_column(Float, default=0.04)


# ---------------------------------------------------------------------------
# LLM Providers
# ---------------------------------------------------------------------------


class LlmProvider(Base):
    __tablename__ = "llm_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    provider_name: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(255))
    model_type: Mapped[str] = mapped_column(String(50), default="chat")
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Agent Configuration
# ---------------------------------------------------------------------------

supervisor_members = None  # Define as secondary table or use explicit model below


class AgentConfig(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str] = mapped_column(String(50), default="standard")
    llm_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True
    )
    max_iterations: Mapped[int] = mapped_column(Integer, default=25)
    summary_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    llm_provider: Mapped[LlmProvider | None] = relationship("LlmProvider", lazy="joined")
    tool_assignments: Mapped[list[AgentToolAssignment]] = relationship("AgentToolAssignment", back_populates="agent", cascade="all, delete-orphan")
    knowledge_graph_assignments: Mapped[list[AgentKnowledgeGraphAssignment]] = relationship("AgentKnowledgeGraphAssignment", back_populates="agent", cascade="all, delete-orphan")
    member_agents: Mapped[list[AgentConfig]] = relationship(
        "AgentConfig",
        secondary="supervisor_members",
        primaryjoin="AgentConfig.id == supervisor_members.c.supervisor_id",
        secondaryjoin="AgentConfig.id == supervisor_members.c.member_id",
    )


class AgentToolAssignment(Base):
    __tablename__ = "agent_tool_assignments"

    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    tool_slug: Mapped[str] = mapped_column(String(100), primary_key=True)

    agent: Mapped[AgentConfig] = relationship("AgentConfig", back_populates="tool_assignments")


from sqlalchemy import Table, Column

supervisor_members = Table(
    "supervisor_members",
    Base.metadata,
    Column("supervisor_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
    Column("member_id", UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
)


# ---------------------------------------------------------------------------
# Knowledge Graphs
# ---------------------------------------------------------------------------


class KnowledgeGraph(Base):
    __tablename__ = "knowledge_graphs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AgentKnowledgeGraphAssignment(Base):
    __tablename__ = "agent_knowledge_graph_assignments"

    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True)
    knowledge_graph_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_graphs.id", ondelete="CASCADE"), primary_key=True)

    agent: Mapped[AgentConfig] = relationship("AgentConfig", back_populates="knowledge_graph_assignments")
    knowledge_graph: Mapped[KnowledgeGraph] = relationship("KnowledgeGraph")


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class MessageRole(enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # --- ADAPT: Change ForeignKey target to your User table ---
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    messages: Mapped[list[ChatMessage]] = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")


# ---------------------------------------------------------------------------
# Agent Activity (delegation tracking)
# ---------------------------------------------------------------------------


class AgentActivity(Base):
    __tablename__ = "agent_activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    trigger_message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    response_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_slug: Mapped[str] = mapped_column(String(100))
    run_id: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Feedback (capability gap reporting)
# ---------------------------------------------------------------------------


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), default="agent")
    category: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    user_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Task Items (structured task decomposition)
# ---------------------------------------------------------------------------


class TaskItem(Base):
    __tablename__ = "task_items"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    owner_agent_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    blocked_by: Mapped[list[str] | None] = mapped_column(ARRAY(String), server_default="{}")
    blocks: Mapped[list[str] | None] = mapped_column(ARRAY(String), server_default="{}")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','in_progress','completed','blocked','cancelled')",
            name="ck_task_items_status",
        ),
    )


# ---------------------------------------------------------------------------
# Agent Memories (structured long-term memory with taxonomy)
# ---------------------------------------------------------------------------


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "type IN ('user', 'feedback', 'project', 'reference')",
            name="ck_agent_memories_type",
        ),
    )
