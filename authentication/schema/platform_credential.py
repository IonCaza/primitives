import uuid
from datetime import datetime, timezone

import enum

from sqlalchemy import String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Platform(str, enum.Enum):
    """Extensible enum for supported external platforms.

    Override or extend this in your app to add platform-specific values.
    """
    GENERIC = "generic"


class PlatformCredential(Base):
    __tablename__ = "platform_credentials"
    __table_args__ = {
        "comment": "Encrypted API token for accessing platform APIs (GitHub, GitLab, Azure DevOps).",
    }

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Auto-generated unique identifier")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Human-readable label for the credential")
    platform: Mapped[Platform] = mapped_column(SAEnum(Platform, create_constraint=False, native_enum=False), nullable=False, comment="Target platform (github, gitlab, azure)")
    token_encrypted: Mapped[str] = mapped_column(String(4096), nullable=False, comment="Fernet-encrypted API access token")
    base_url: Mapped[str | None] = mapped_column(String(2048), comment="Custom API base URL for self-hosted instances")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="User who created this credential")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), comment="Timestamp when the credential was created")

    created_by_user = relationship("User")
