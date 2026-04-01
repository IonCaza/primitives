"""OIDC authentication provider -- handles initiate and callback flows with JIT provisioning."""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.providers.base import AuthResult
from app.db.models.oidc_provider import OidcProvider
from app.db.models.user import User
from app.services import oidc as oidc_service

logger = logging.getLogger(__name__)


async def initiate(provider: OidcProvider, redirect_uri: str) -> str:
    """Build the authorization URL and persist PKCE state. Returns the full redirect URL."""
    url, _state = await oidc_service.build_authorization_url(provider, redirect_uri)
    return url


async def complete(
    provider: OidcProvider,
    code: str,
    state: str,
    redirect_uri: str,
    db: AsyncSession,
) -> AuthResult:
    """Exchange the code, validate the ID token, provision or update the user, and return an AuthResult."""
    state_data = await oidc_service.validate_state(state)
    if state_data is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OIDC state")

    if state_data.get("provider_id") != str(provider.id):
        raise HTTPException(status_code=400, detail="State/provider mismatch")

    code_verifier = state_data["code_verifier"]

    tokens = await oidc_service.exchange_code(provider, code, code_verifier, redirect_uri)
    id_token_raw = tokens.get("id_token")
    if not id_token_raw:
        raise HTTPException(status_code=502, detail="IDP did not return an id_token")

    claims = oidc_service.validate_id_token(provider, id_token_raw)
    user_claims = oidc_service.extract_user_claims(provider, claims)

    if not user_claims.email:
        raise HTTPException(status_code=502, detail="IDP did not provide an email claim")

    user = await _find_or_provision(provider, user_claims, db)
    return AuthResult(user=user, requires_mfa=False)


async def _find_or_provision(
    provider: OidcProvider,
    claims: oidc_service.UserClaims,
    db: AsyncSession,
) -> User:
    stmt = select(User).where(
        User.oidc_provider_id == provider.id,
        User.oidc_subject == claims.subject,
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is not None:
        changed = False
        if claims.email and user.email != claims.email:
            existing = await db.execute(select(User).where(User.email == claims.email, User.id != user.id))
            if existing.scalar_one_or_none() is None:
                user.email = claims.email
                changed = True
        if claims.full_name and user.full_name != claims.full_name:
            user.full_name = claims.full_name
            changed = True
        if user.is_admin != claims.is_admin:
            user.is_admin = claims.is_admin
            changed = True
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")
        if changed:
            await db.commit()
            await db.refresh(user)
        return user

    if not provider.auto_provision:
        raise HTTPException(status_code=403, detail="Auto-provisioning is disabled for this provider")

    username = await _generate_username(claims.email, db)
    user = User(
        email=claims.email,
        username=username,
        hashed_password=None,
        full_name=claims.full_name,
        is_admin=claims.is_admin,
        auth_provider="oidc",
        oidc_provider_id=provider.id,
        oidc_subject=claims.subject,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("JIT-provisioned user %s from OIDC provider %s", username, provider.slug)
    return user


async def _generate_username(email: str, db: AsyncSession) -> str:
    base = re.sub(r"[^a-zA-Z0-9._-]", "", email.split("@")[0])
    if not base:
        base = "user"
    candidate = base
    suffix = 1
    while True:
        existing = await db.execute(select(User).where(User.username == candidate))
        if existing.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base}{suffix}"
        suffix += 1
