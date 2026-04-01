import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import User
from app.db.models.smtp_settings import SmtpSettings, SINGLETON_ID
from app.auth.dependencies import require_admin
from app.services.encryption import _get_fernet
from app.services.email import send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/smtp", tags=["smtp-settings"])


# ── Schemas ──────────────────────────────────────────────────────────────

class SmtpSettingsOut(BaseModel):
    host: str
    port: int
    username: str
    has_password: bool
    from_email: str
    from_name: str
    use_tls: bool
    enabled: bool


class SmtpSettingsUpdate(BaseModel):
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    use_tls: bool | None = None
    enabled: bool | None = None


class SmtpTestRequest(BaseModel):
    to: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────

async def _get_or_create(db: AsyncSession) -> SmtpSettings:
    result = await db.execute(select(SmtpSettings).where(SmtpSettings.id == SINGLETON_ID))
    row = result.scalar_one_or_none()
    if row is None:
        row = SmtpSettings(id=SINGLETON_ID)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("", response_model=SmtpSettingsOut)
async def get_smtp_settings(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = await _get_or_create(db)
    return SmtpSettingsOut(
        host=row.host,
        port=row.port,
        username=row.username,
        has_password=bool(row.password_encrypted),
        from_email=row.from_email,
        from_name=row.from_name,
        use_tls=row.use_tls,
        enabled=row.enabled,
    )


@router.put("", response_model=SmtpSettingsOut)
async def update_smtp_settings(
    body: SmtpSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = await _get_or_create(db)

    if body.host is not None:
        row.host = body.host
    if body.port is not None:
        row.port = body.port
    if body.username is not None:
        row.username = body.username
    if body.password is not None and body.password != "":
        row.password_encrypted = _get_fernet().encrypt(body.password.encode()).decode()
    if body.from_email is not None:
        row.from_email = body.from_email
    if body.from_name is not None:
        row.from_name = body.from_name
    if body.use_tls is not None:
        row.use_tls = body.use_tls
    if body.enabled is not None:
        row.enabled = body.enabled

    await db.commit()
    await db.refresh(row)

    return SmtpSettingsOut(
        host=row.host,
        port=row.port,
        username=row.username,
        has_password=bool(row.password_encrypted),
        from_email=row.from_email,
        from_name=row.from_name,
        use_tls=row.use_tls,
        enabled=row.enabled,
    )


@router.post("/test", status_code=status.HTTP_200_OK)
async def test_smtp(
    body: SmtpTestRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    recipient = body.to or admin.email
    try:
        await send_email(
            to=recipient,
            subject="SMTP Test",
            html_body="<p>This is a test email. Your SMTP configuration is working correctly.</p>",
            text_body="This is a test email. Your SMTP configuration is working correctly.",
            db=db,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("SMTP test failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"SMTP error: {e}")
    return {"detail": f"Test email sent to {recipient}"}
