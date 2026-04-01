import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEFAULT_CLAIM_MAPPING = {
    "email": "email",
    "name": "name",
    "groups": "groups",
    "admin_groups": [],
}


class OidcProvider(Base):
    """OIDC/OAuth2 identity provider configuration."""
    __tablename__ = "oidc_providers"
    __table_args__ = {
        "comment": "Configured OIDC/OAuth2 identity providers (Keycloak, Azure Entra, etc.).",
    }

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    client_id: Mapped[str] = mapped_column(String(512), nullable=False)
    client_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    discovery_url: Mapped[str | None] = mapped_column(String(2048))
    authorization_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    token_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    userinfo_url: Mapped[str | None] = mapped_column(String(2048))
    jwks_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    scopes: Mapped[str] = mapped_column(String(500), nullable=False, default="openid profile email")
    claim_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: dict(DEFAULT_CLAIM_MAPPING))
    auto_provision: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
