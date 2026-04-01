import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SSHCredential(Base):
    __tablename__ = "ssh_credentials"
    __table_args__ = {
        "comment": "Encrypted SSH key pair used for cloning Git repositories over SSH.",
    }

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Auto-generated unique identifier")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Human-readable label for the SSH key")
    key_type: Mapped[str] = mapped_column(String(20), nullable=False, default="ed25519", comment="SSH key algorithm (ed25519 or rsa)")
    public_key: Mapped[str] = mapped_column(Text, nullable=False, comment="SSH public key in OpenSSH format")
    private_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False, comment="Fernet-encrypted SSH private key")
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, comment="SSH key fingerprint for identification")
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="User who generated this SSH key")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), comment="Timestamp when the key was generated")

    created_by_user = relationship("User", back_populates="ssh_credentials")
