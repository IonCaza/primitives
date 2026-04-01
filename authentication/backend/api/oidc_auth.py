"""Public OIDC authentication flow endpoints (authorize redirect + callback)."""

from __future__ import annotations

import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_db
from app.db.models.oidc_provider import OidcProvider
from app.auth.providers.oidc import initiate, complete
from app.auth.security import create_access_token, create_refresh_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oidc", tags=["oidc-auth"])


async def _get_enabled_provider(slug: str, db: AsyncSession) -> OidcProvider:
    result = await db.execute(
        select(OidcProvider).where(OidcProvider.slug == slug, OidcProvider.enabled == True)  # noqa: E712
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="OIDC provider not found or not enabled")
    return provider


@router.get("/{slug}/authorize")
async def authorize(
    slug: str,
    redirect_uri: str = Query(..., description="Frontend callback URL"),
    db: AsyncSession = Depends(get_db),
):
    provider = await _get_enabled_provider(slug, db)
    backend_callback = f"{settings.backend_url}/api/auth/oidc/{slug}/callback"
    authorization_url = await initiate(provider, backend_callback)
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/{slug}/callback")
async def callback(
    slug: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    provider = await _get_enabled_provider(slug, db)
    backend_callback = f"{settings.backend_url}/api/auth/oidc/{slug}/callback"

    auth_result = await complete(provider, code, state, backend_callback, db)
    user = auth_result.user

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    fragment = urllib.parse.urlencode({
        "access_token": access_token,
        "refresh_token": refresh_token,
    })
    redirect_url = f"{settings.frontend_url}/auth/oidc/callback#{fragment}"
    return RedirectResponse(url=redirect_url, status_code=302)
