import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import User
from app.db.models.smtp_settings import SmtpSettings
from app.auth.dependencies import get_current_user, get_mfa_setup_user
from app.auth.security import verify_password, create_access_token, create_refresh_token
from app.services.mfa import (
    generate_totp_secret,
    get_totp_provisioning_uri,
    generate_qr_code_base64,
    verify_totp,
    encrypt_totp_secret,
    decrypt_totp_secret,
    generate_email_otp,
    store_email_otp,
    check_otp_cooldown,
    verify_email_otp,
    generate_recovery_codes,
    hash_recovery_codes,
)
from app.services.email import send_templated_email

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])


# ── Schemas ──────────────────────────────────────────────────────────────

class TotpInitResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_code_base64: str


class TotpConfirmRequest(BaseModel):
    secret: str
    code: str


class EmailOtpConfirmRequest(BaseModel):
    code: str


class MfaSetupCompleteResponse(BaseModel):
    recovery_codes: list[str]
    mfa_method: str
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"


class PasswordConfirmRequest(BaseModel):
    password: str


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def _smtp_enabled(db: AsyncSession) -> bool:
    result = await db.execute(select(SmtpSettings).limit(1))
    smtp = result.scalar_one_or_none()
    return bool(smtp and smtp.enabled and smtp.host)


# ── Setup Options ────────────────────────────────────────────────────────

class MfaOptionsResponse(BaseModel):
    totp: bool
    email: bool


@router.get("/setup/options", response_model=MfaOptionsResponse)
async def mfa_setup_options(
    user: User = Depends(get_mfa_setup_user),
    db: AsyncSession = Depends(get_db),
):
    """Return which MFA methods are available for this user."""
    smtp_ok = await _smtp_enabled(db)
    has_email = bool(user.email and _EMAIL_RE.match(user.email))
    return MfaOptionsResponse(totp=True, email=smtp_ok and has_email)


# ── TOTP Setup ───────────────────────────────────────────────────────────

@router.post("/setup/totp/init", response_model=TotpInitResponse)
async def totp_init(user: User = Depends(get_mfa_setup_user)):
    secret = generate_totp_secret()
    uri = get_totp_provisioning_uri(secret, user.email)
    qr = generate_qr_code_base64(uri)
    return TotpInitResponse(secret=secret, provisioning_uri=uri, qr_code_base64=qr)


@router.post("/setup/totp/confirm", response_model=MfaSetupCompleteResponse)
async def totp_confirm(
    body: TotpConfirmRequest,
    user: User = Depends(get_mfa_setup_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_totp(body.secret, body.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")

    already_had_mfa = user.mfa_enabled and user.mfa_setup_complete
    user.totp_secret_encrypted = encrypt_totp_secret(body.secret)
    user.mfa_enabled = True
    user.mfa_method = "totp"
    user.mfa_setup_complete = True

    codes: list[str] = []
    if not user.mfa_recovery_codes_encrypted:
        codes = generate_recovery_codes()
        user.mfa_recovery_codes_encrypted = hash_recovery_codes(codes)
    await db.commit()

    return MfaSetupCompleteResponse(
        recovery_codes=codes,
        mfa_method="totp",
        access_token=None if already_had_mfa else create_access_token(str(user.id)),
        refresh_token=None if already_had_mfa else create_refresh_token(str(user.id)),
    )


# ── Email OTP Setup ─────────────────────────────────────────────────────

@router.post("/setup/email/init", status_code=status.HTTP_200_OK)
async def email_otp_init(
    user: User = Depends(get_mfa_setup_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.email or not _EMAIL_RE.match(user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid email address is required for email-based MFA. Update your email in account settings first.",
        )
    if not await _smtp_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is not configured. Contact your administrator or use an authenticator app instead.",
        )

    remaining = await check_otp_cooldown(str(user.id))
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {remaining} seconds before requesting a new code.",
        )

    code = generate_email_otp()
    await store_email_otp(str(user.id), code)
    try:
        await send_templated_email(user.email, "otp_code", {"code": code, "username": user.username}, db)
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to send OTP email. Check SMTP configuration.")
    return {"detail": "Verification code sent to your email"}


@router.post("/setup/email/confirm", response_model=MfaSetupCompleteResponse)
async def email_otp_confirm(
    body: EmailOtpConfirmRequest,
    user: User = Depends(get_mfa_setup_user),
    db: AsyncSession = Depends(get_db),
):
    valid = await verify_email_otp(str(user.id), body.code)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification code")

    already_had_mfa = user.mfa_enabled and user.mfa_setup_complete
    user.email_mfa_enabled = True
    user.mfa_enabled = True
    user.mfa_method = "email"
    user.mfa_setup_complete = True

    codes: list[str] = []
    if not user.mfa_recovery_codes_encrypted:
        codes = generate_recovery_codes()
        user.mfa_recovery_codes_encrypted = hash_recovery_codes(codes)
    await db.commit()

    return MfaSetupCompleteResponse(
        recovery_codes=codes,
        mfa_method="email",
        access_token=None if already_had_mfa else create_access_token(str(user.id)),
        refresh_token=None if already_had_mfa else create_refresh_token(str(user.id)),
    )


# ── Disable MFA ──────────────────────────────────────────────────────────

@router.post("/disable", status_code=status.HTTP_200_OK)
async def disable_mfa(
    body: PasswordConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    user.mfa_enabled = False
    user.mfa_method = None
    user.totp_secret_encrypted = None
    user.email_mfa_enabled = False
    user.mfa_recovery_codes_encrypted = None
    user.mfa_setup_complete = False
    await db.commit()
    return {"detail": "MFA disabled"}


# ── Recovery Codes ───────────────────────────────────────────────────────

@router.post("/recovery-codes", response_model=RecoveryCodesResponse)
async def regenerate_recovery_codes(
    body: PasswordConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    if not user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled")

    codes = generate_recovery_codes()
    user.mfa_recovery_codes_encrypted = hash_recovery_codes(codes)
    await db.commit()
    return RecoveryCodesResponse(recovery_codes=codes)
