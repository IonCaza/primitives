"""Access policy and resource grant models for hierarchical RBAC.

AccessPolicy stores configurable rules at platform / organization / team / user
scope.  ResourceGrant records explicit per-resource sharing between users.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccessPolicy(Base):
    __tablename__ = "access_policies"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", name="uq_access_policy_scope"),
        {
            "comment": (
                "Hierarchical access-control policy.  Exactly one row per scope "
                "(platform / org / team / user).  Null fields mean 'inherit from "
                "the next broader scope'."
            ),
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        comment="Auto-generated unique identifier",
    )
    scope_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="Hierarchy level: platform, organization, team, or user",
    )
    scope_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="FK to the entity (org/team/user id).  Null for platform scope.",
    )

    data_scope: Mapped[str | None] = mapped_column(
        String(10), nullable=True,
        comment="Effective data visibility: own, team, org, all.  Null = inherit.",
    )
    agent_tool_rules: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment='Per-agent tool allow-list.  Example: {"text-to-sql": ["list_tables"]}. Null = inherit.',
    )
    sql_allowed_tables: Mapped[list | None] = mapped_column(
        JSON, nullable=True,
        comment="Explicit table allow-list for text-to-SQL agent.  Null = all visible.",
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
        comment="User who created or last modified this policy",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="Row creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="Last modification timestamp",
    )


class ResourceGrant(Base):
    __tablename__ = "resource_grants"
    __table_args__ = (
        UniqueConstraint(
            "resource_type", "resource_id", "granted_to_user_id",
            name="uq_resource_grant_target",
        ),
        Index("ix_resource_grant_grantee", "granted_to_user_id"),
        {
            "comment": (
                "Explicit per-resource sharing.  Additive: grants expand a "
                "user's access beyond what their policy scope provides."
            ),
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        comment="Auto-generated unique identifier",
    )
    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Logical type of the shared resource (appraisal, project, …)",
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False,
        comment="Primary key of the shared resource",
    )
    granted_to_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        comment="User who receives the grant",
    )
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
        comment="User who created the grant",
    )
    permission: Mapped[str] = mapped_column(
        String(20), nullable=False, default="view",
        comment="Permission level: view, edit, admin",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Optional expiry.  Null = permanent until explicitly revoked.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        comment="Row creation timestamp",
    )
