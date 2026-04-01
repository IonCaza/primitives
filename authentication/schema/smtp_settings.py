import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


class SmtpSettings(Base):
    """Single-row SMTP configuration for outbound email."""
    __tablename__ = "smtp_settings"
    __table_args__ = {
        "comment": "Single-row SMTP configuration for sending outbound emails.",
    }

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=SINGLETON_ID)
    host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    username: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    password_encrypted: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    from_email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    from_name: Mapped[str] = mapped_column(String(255), default="MyApp", nullable=False)
    use_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
