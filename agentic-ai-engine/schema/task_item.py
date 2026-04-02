import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskItem(Base):
    __tablename__ = "task_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','in_progress','completed','blocked','cancelled')",
            name="ck_task_items_status",
        ),
        {
            "comment": "Structured task decomposition items scoped to a chat session.",
        },
    )

    id: Mapped[str] = mapped_column(String(8), primary_key=True, comment="Session-scoped sequential ID (e.g. t1, t2)")
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        primary_key=True, comment="Chat session this task belongs to",
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False, comment="Short title describing the task")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Detailed description with specifics")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="Current status: pending, in_progress, completed, blocked, cancelled")
    owner_agent_slug: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Agent slug assigned to this task")
    blocked_by: Mapped[list[str] | None] = mapped_column(ARRAY(String), server_default="{}", comment="Task IDs that must complete before this one")
    blocks: Mapped[list[str] | None] = mapped_column(ARRAY(String), server_default="{}", comment="Task IDs that depend on this one")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, server_default="{}", comment="Arbitrary metadata for extensions")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), comment="Creation timestamp")
