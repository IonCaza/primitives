from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User


@dataclass
class AuthResult:
    user: User
    requires_mfa: bool = False
    mfa_method: str | None = None
    mfa_methods: list[str] | None = None
    requires_mfa_setup: bool = False
    requires_password_change: bool = False


class AuthProvider(ABC):
    """Base class for pluggable authentication providers."""

    @abstractmethod
    async def authenticate(self, credentials: dict, db: AsyncSession) -> AuthResult:
        """Validate credentials and return an AuthResult.

        Raises HTTPException on failure.
        """
        ...
