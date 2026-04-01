import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")


class AuthSettings(Base):
    """Single-row global authentication settings."""
    __tablename__ = "auth_settings"
    __table_args__ = {
        "comment": "Single-row global authentication/MFA policy settings.",
    }

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=SINGLETON_ID)
    force_mfa_local_auth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    local_login_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
