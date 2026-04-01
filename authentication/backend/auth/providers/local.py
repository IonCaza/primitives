from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.models.auth_settings import AuthSettings, SINGLETON_ID as AUTH_SETTINGS_ID
from app.auth.security import verify_password
from app.auth.providers.base import AuthProvider, AuthResult


class LocalAuthProvider(AuthProvider):
    """Username + password authentication against the local database."""

    async def authenticate(self, credentials: dict, db: AsyncSession) -> AuthResult:
        username = credentials.get("username", "")
        password = credentials.get("password", "")

        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if user is None or not user.hashed_password or not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )

        if user.must_change_password:
            return AuthResult(user=user, requires_password_change=True)

        if user.mfa_enabled and user.mfa_setup_complete:
            return AuthResult(
                user=user,
                requires_mfa=True,
                mfa_method=user.mfa_method,
                mfa_methods=user.mfa_methods,
            )

        auth_row = await db.execute(
            select(AuthSettings).where(AuthSettings.id == AUTH_SETTINGS_ID)
        )
        auth_settings = auth_row.scalar_one_or_none()
        force_mfa = auth_settings.force_mfa_local_auth if auth_settings else False

        if force_mfa and not user.mfa_setup_complete:
            return AuthResult(user=user, requires_mfa_setup=True)

        return AuthResult(user=user)
