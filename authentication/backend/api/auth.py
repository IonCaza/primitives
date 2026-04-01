import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
import re
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import User
from app.db.models.oidc_provider import OidcProvider
from app.auth.security import (
    hash_password,
    create_access_token,
    create_refresh_token,
    create_mfa_challenge_token,
    create_mfa_setup_token,
    create_password_change_token,
    decode_token,
)
from app.db.models.auth_settings import AuthSettings, SINGLETON_ID as AUTH_SETTINGS_ID
from app.auth.dependencies import get_current_user, require_admin
from app.auth.providers.local import LocalAuthProvider
from app.services.mfa import (
    verify_totp,
    decrypt_totp_secret,
    verify_email_otp,
    verify_recovery_code,
    generate_email_otp,
    store_email_otp,
    check_otp_cooldown,
)
from app.services.email import send_templated_email

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_local_provider = LocalAuthProvider()


# ── Schemas ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Not a valid email address")
        return v.lower().strip()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MfaChallengeResponse(BaseModel):
    requires_mfa: bool = True
    mfa_token: str
    mfa_method: str | None = None
    mfa_methods: list[str] = []


class MfaSetupRequiredResponse(BaseModel):
    requires_mfa_setup: bool = True
    mfa_setup_token: str


class PasswordChangeRequiredResponse(BaseModel):
    password_change_required: bool = True
    password_change_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    full_name: str | None
    is_admin: bool
    is_active: bool
    auth_provider: str
    mfa_enabled: bool
    mfa_method: str | None
    mfa_methods: list[str] = []
    mfa_setup_complete: bool

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: str | None = None
    is_admin: bool = False
    send_invite: bool = False
    temporary_password: bool = False

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Not a valid email address")
        return v.lower().strip()


class UpdateUserRequest(BaseModel):
    email: str | None = None
    username: str | None = None
    full_name: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is not None:
            if not _EMAIL_RE.match(v):
                raise ValueError("Not a valid email address")
            return v.lower().strip()
        return v


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str
    method: str  # "totp", "email", "recovery"


class MfaSendEmailOtpRequest(BaseModel):
    mfa_token: str


class ChangePasswordRequest(BaseModel):
    token: str
    new_password: str


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """First-run registration. Only works when no users exist (creates admin)."""
    count = await db.scalar(select(func.count()).select_from(User))
    if count and count > 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration closed. Ask an admin to create your account.")
    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_admin=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    auth_result = await _local_provider.authenticate(
        {"username": body.username, "password": body.password}, db
    )
    user = auth_result.user

    row = await db.execute(select(AuthSettings).where(AuthSettings.id == AUTH_SETTINGS_ID))
    auth_settings = row.scalar_one_or_none()
    if auth_settings and not auth_settings.local_login_enabled and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local login is disabled. Please use an external identity provider.",
        )

    if auth_result.requires_password_change:
        return PasswordChangeRequiredResponse(
            password_change_token=create_password_change_token(str(user.id)),
        )

    if auth_result.requires_mfa:
        return MfaChallengeResponse(
            mfa_token=create_mfa_challenge_token(str(user.id)),
            mfa_method=auth_result.mfa_method,
            mfa_methods=user.mfa_methods,
        )

    if auth_result.requires_mfa_setup:
        return MfaSetupRequiredResponse(
            mfa_setup_token=create_mfa_setup_token(str(user.id)),
        )

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


class OidcProviderPublicItem(BaseModel):
    slug: str
    name: str
    provider_type: str


class AuthProvidersResponse(BaseModel):
    local_login_enabled: bool
    oidc_providers: list[OidcProviderPublicItem]


@router.get("/providers", response_model=AuthProvidersResponse)
async def list_auth_providers(db: AsyncSession = Depends(get_db)):
    """Public endpoint -- returns what login options are available."""
    row = await db.execute(select(AuthSettings).where(AuthSettings.id == AUTH_SETTINGS_ID))
    auth_settings = row.scalar_one_or_none()
    local_enabled = auth_settings.local_login_enabled if auth_settings else True

    result = await db.execute(
        select(OidcProvider).where(OidcProvider.enabled == True).order_by(OidcProvider.name)  # noqa: E712
    )
    providers = result.scalars().all()

    return AuthProvidersResponse(
        local_login_enabled=local_enabled,
        oidc_providers=[
            OidcProviderPublicItem(slug=p.slug, name=p.name, provider_type=p.provider_type)
            for p in providers
        ],
    )


@router.post("/mfa/verify", response_model=TokenResponse)
async def mfa_verify(body: MfaVerifyRequest, db: AsyncSession = Depends(get_db)):
    """Verify an MFA code during login and issue full tokens."""
    payload = decode_token(body.mfa_token)
    if payload is None or payload.get("type") != "mfa_challenge":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired MFA token")

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    verified = False
    if body.method == "totp":
        if user.totp_secret_encrypted:
            secret = decrypt_totp_secret(user.totp_secret_encrypted)
            verified = verify_totp(secret, body.code)
    elif body.method == "email":
        verified = await verify_email_otp(str(user.id), body.code)
    elif body.method == "recovery":
        if user.mfa_recovery_codes_encrypted:
            verified, updated = verify_recovery_code(user.mfa_recovery_codes_encrypted, body.code)
            if verified:
                user.mfa_recovery_codes_encrypted = updated
                await db.commit()

    if not verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/mfa/send-email-otp", status_code=status.HTTP_200_OK)
async def mfa_send_email_otp(body: MfaSendEmailOtpRequest, db: AsyncSession = Depends(get_db)):
    """Send an email OTP during the MFA challenge login flow."""
    payload = decode_token(body.mfa_token)
    if payload is None or payload.get("type") not in ("mfa_challenge", "mfa_setup"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired MFA token")

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

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

    return {"detail": "OTP sent"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)):
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/change-password", response_model=TokenResponse)
async def change_password(body: ChangePasswordRequest, db: AsyncSession = Depends(get_db)):
    """Accept a password-change token and set a new password, clearing the temporary flag."""
    payload = decode_token(body.token)
    if payload is None or payload.get("type") != "password_change":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired password change token")

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


class MeResponse(UserResponse):
    mfa_setup_required: bool = False

@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    force_mfa = False
    if user.auth_provider == "local" and not user.mfa_setup_complete:
        row = await db.execute(select(AuthSettings).where(AuthSettings.id == AUTH_SETTINGS_ID))
        auth_settings = row.scalar_one_or_none()
        if auth_settings and auth_settings.force_mfa_local_auth:
            force_mfa = True
    return MeResponse(
        id=user.id, email=user.email, username=user.username,
        full_name=user.full_name, is_admin=user.is_admin, is_active=user.is_active,
        auth_provider=user.auth_provider, mfa_enabled=user.mfa_enabled,
        mfa_method=user.mfa_method, mfa_methods=user.mfa_methods,
        mfa_setup_complete=user.mfa_setup_complete,
        mfa_setup_required=force_mfa,
    )


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v is not None and not _EMAIL_RE.match(v):
            raise ValueError("Not a valid email address")
        return v.lower().strip() if v else v


@router.put("/me", response_model=MeResponse)
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.email is not None and body.email != user.email:
        dup = await db.execute(select(User).where(User.email == body.email, User.id != user.id))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already taken")
        user.email = body.email
    if body.full_name is not None:
        user.full_name = body.full_name
    await db.commit()
    await db.refresh(user)

    force_mfa = False
    if user.auth_provider == "local" and not user.mfa_setup_complete:
        row = await db.execute(select(AuthSettings).where(AuthSettings.id == AUTH_SETTINGS_ID))
        auth_settings = row.scalar_one_or_none()
        if auth_settings and auth_settings.force_mfa_local_auth:
            force_mfa = True
    return MeResponse(
        id=user.id, email=user.email, username=user.username,
        full_name=user.full_name, is_admin=user.is_admin, is_active=user.is_active,
        auth_provider=user.auth_provider, mfa_enabled=user.mfa_enabled,
        mfa_method=user.mfa_method, mfa_methods=user.mfa_methods,
        mfa_setup_complete=user.mfa_setup_complete,
        mfa_setup_required=force_mfa,
    )


class ChangeOwnPasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/me/password", status_code=status.HTTP_200_OK)
async def change_own_password(
    body: ChangeOwnPasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.auth_provider != "local":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password changes are only available for local accounts")
    if not user.hashed_password or not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")
    user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return {"detail": "Password changed successfully"}


@router.get("/users", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db), _admin: User = Depends(require_admin)):
    result = await db.execute(select(User).order_by(User.created_at))
    return result.scalars().all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    existing = await db.execute(select(User).where((User.email == body.email) | (User.username == body.username)))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email or username already taken")
    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_admin=body.is_admin,
        must_change_password=body.temporary_password,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if body.send_invite:
        login_url = request.headers.get("referer", "").rstrip("/").split("/settings")[0] or str(request.base_url).rstrip("/")
        login_url = login_url.rstrip("/") + "/login"
        try:
            await send_templated_email(
                user.email,
                "user_invite",
                {
                    "username": user.username,
                    "email": user.email,
                    "password": body.password,
                    "login_url": login_url,
                },
                db,
            )
        except Exception:
            pass

    return user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.email is not None and body.email != target.email:
        dup = await db.execute(select(User).where(User.email == body.email, User.id != user_id))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already taken")
        target.email = body.email
    if body.username is not None and body.username != target.username:
        dup = await db.execute(select(User).where(User.username == body.username, User.id != user_id))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
        target.username = body.username
    if body.full_name is not None:
        target.full_name = body.full_name
    if body.is_admin is not None:
        if user_id == admin.id and not body.is_admin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot revoke your own admin privileges")
        target.is_admin = body.is_admin
    if body.is_active is not None:
        if user_id == admin.id and not body.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate yourself")
        target.is_active = body.is_active
    if body.password is not None and body.password:
        target.hashed_password = hash_password(body.password)

    await db.commit()
    await db.refresh(target)
    return target


@router.post("/users/{user_id}/mfa/reset", response_model=UserResponse)
async def admin_reset_mfa(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.mfa_enabled = False
    target.mfa_method = None
    target.totp_secret_encrypted = None
    target.email_mfa_enabled = False
    target.mfa_recovery_codes_encrypted = None
    target.mfa_setup_complete = False
    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.delete(user)
    await db.commit()
