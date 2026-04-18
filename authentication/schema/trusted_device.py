import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TrustedDevice(Base):
    """A device that has completed MFA and is trusted to skip MFA on subsequent logins.

    The raw token is never stored; only its SHA-256 hash. When a user ticks
    "Remember this device" on the MFA verify step, a random 32-byte url-safe
    token is generated, hashed, and persisted here. The raw token is returned
    once to the client and stored in ``localStorage`` on that device.

    On future logins, the client sends the raw token alongside username+password;
    if it hashes to a non-expired row bound to the authenticating user, the MFA
    challenge is skipped entirely for that login.

    Trusted devices are revoked on:
      - explicit user action (self-service list/revoke)
      - password change (self-service or forced)
      - MFA disable
      - admin MFA reset
    """

    __tablename__ = "trusted_devices"
    __table_args__ = (
        Index("ix_trusted_devices_user_id", "user_id"),
        Index("ix_trusted_devices_expires_at", "expires_at"),
        {"comment": "Devices that completed MFA and are trusted to skip MFA until expires_at."},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Auto-generated unique identifier")
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="User this trusted device belongs to")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="SHA-256 hex of the raw trust token")
    device_label: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Optional human-readable label (e.g., 'Work laptop')")
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="User-Agent captured when the device was trusted")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="IP address captured when the device was trusted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, comment="When this device was marked trusted")
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, comment="Last time this token was used to skip MFA")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="After this moment the token is invalid")

    user = relationship("User", back_populates="trusted_devices")
