import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("oidc_provider_id", "oidc_subject", name="uq_user_oidc_identity"),
        {"comment": "Application user account with authentication credentials and admin flag."},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Auto-generated unique identifier")
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False, comment="User email address, used for login")
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False, comment="Unique login username")
    hashed_password: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="Bcrypt-hashed password (null for OIDC users)")
    full_name: Mapped[str | None] = mapped_column(String(255), comment="Optional display name")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, comment="Whether the user has administrative privileges")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="Whether the account is enabled for login")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), comment="Timestamp when the account was created")

    auth_provider: Mapped[str] = mapped_column(String(50), default="local", nullable=False, comment="Authentication provider (local, oidc, etc.)")
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="Whether MFA is enabled for this user")
    mfa_method: Mapped[str | None] = mapped_column(String(20), comment="Preferred/last-enrolled MFA method: totp or email")
    totp_secret_encrypted: Mapped[str | None] = mapped_column(String(2048), comment="Fernet-encrypted TOTP secret for authenticator apps")
    email_mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", comment="Whether email OTP is enrolled as an MFA method")
    mfa_recovery_codes_encrypted: Mapped[str | None] = mapped_column(Text, comment="Fernet-encrypted JSON array of bcrypt-hashed recovery codes")
    mfa_setup_complete: Mapped[bool] = mapped_column(Boolean, default=False, comment="Whether MFA setup has been completed by the user")

    @property
    def mfa_methods(self) -> list[str]:
        """Return list of enrolled MFA methods."""
        methods: list[str] = []
        if self.totp_secret_encrypted:
            methods.append("totp")
        if self.email_mfa_enabled:
            methods.append("email")
        return methods
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, comment="Whether user must change password on next login (temporary password)")

    oidc_provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("oidc_providers.id", ondelete="SET NULL"), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Subject claim from the OIDC ID token")

    ssh_credentials = relationship("SSHCredential", back_populates="created_by_user", cascade="all, delete-orphan", passive_deletes=True)
    oidc_provider = relationship("OidcProvider")
