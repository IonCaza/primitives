from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import User
from app.db.models.auth_settings import AuthSettings, SINGLETON_ID
from app.auth.dependencies import require_admin

router = APIRouter(prefix="/settings/auth", tags=["auth-settings"])


# ── Schemas ──────────────────────────────────────────────────────────────

class AuthSettingsOut(BaseModel):
    force_mfa_local_auth: bool
    local_login_enabled: bool


class AuthSettingsUpdate(BaseModel):
    force_mfa_local_auth: bool | None = None
    local_login_enabled: bool | None = None


# ── Helpers ──────────────────────────────────────────────────────────────

async def _get_or_create(db: AsyncSession) -> AuthSettings:
    result = await db.execute(select(AuthSettings).where(AuthSettings.id == SINGLETON_ID))
    row = result.scalar_one_or_none()
    if row is None:
        row = AuthSettings(id=SINGLETON_ID)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("", response_model=AuthSettingsOut)
async def get_auth_settings(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = await _get_or_create(db)
    return AuthSettingsOut(
        force_mfa_local_auth=row.force_mfa_local_auth,
        local_login_enabled=row.local_login_enabled,
    )


@router.put("", response_model=AuthSettingsOut)
async def update_auth_settings(
    body: AuthSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = await _get_or_create(db)
    if body.force_mfa_local_auth is not None:
        row.force_mfa_local_auth = body.force_mfa_local_auth
    if body.local_login_enabled is not None:
        row.local_login_enabled = body.local_login_enabled
    await db.commit()
    await db.refresh(row)
    return AuthSettingsOut(
        force_mfa_local_auth=row.force_mfa_local_auth,
        local_login_enabled=row.local_login_enabled,
    )
