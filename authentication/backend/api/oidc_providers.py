"""Admin CRUD for OIDC identity providers."""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models.oidc_provider import OidcProvider
from app.db.models.user import User
from app.auth.dependencies import require_admin
from app.services.encryption import _get_fernet
from app.services import oidc as oidc_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings/oidc-providers", tags=["oidc-providers"])


# ── Schemas ──────────────────────────────────────────────────────────────

class OidcProviderListItem(BaseModel):
    id: str
    slug: str
    name: str
    provider_type: str
    enabled: bool

    class Config:
        from_attributes = True


class ClaimMappingSchema(BaseModel):
    email: str = "email"
    name: str = "name"
    groups: str = "groups"
    admin_groups: list[str] = []


class OidcProviderOut(BaseModel):
    id: str
    slug: str
    name: str
    provider_type: str
    client_id: str
    has_client_secret: bool
    discovery_url: str | None
    authorization_url: str
    token_url: str
    userinfo_url: str | None
    jwks_url: str
    scopes: str
    claim_mapping: ClaimMappingSchema
    auto_provision: bool
    enabled: bool


class OidcProviderCreate(BaseModel):
    name: str
    provider_type: str
    client_id: str
    client_secret: str | None = None
    discovery_url: str | None = None
    authorization_url: str = ""
    token_url: str = ""
    userinfo_url: str | None = None
    jwks_url: str = ""
    scopes: str = "openid profile email"
    claim_mapping: ClaimMappingSchema = ClaimMappingSchema()
    auto_provision: bool = True
    enabled: bool = False


class OidcProviderUpdate(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    discovery_url: str | None = None
    authorization_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    jwks_url: str | None = None
    scopes: str | None = None
    claim_mapping: ClaimMappingSchema | None = None
    auto_provision: bool | None = None
    enabled: bool | None = None


class DiscoverRequest(BaseModel):
    discovery_url: str


class DiscoverResponse(BaseModel):
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None
    jwks_uri: str
    issuer: str


# ── Helpers ──────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "provider"


async def _unique_slug(base_slug: str, db: AsyncSession, exclude_id: uuid.UUID | None = None) -> str:
    candidate = base_slug
    suffix = 1
    while True:
        stmt = select(OidcProvider).where(OidcProvider.slug == candidate)
        if exclude_id:
            stmt = stmt.where(OidcProvider.id != exclude_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _to_out(p: OidcProvider) -> OidcProviderOut:
    return OidcProviderOut(
        id=str(p.id),
        slug=p.slug,
        name=p.name,
        provider_type=p.provider_type,
        client_id=p.client_id,
        has_client_secret=bool(p.client_secret_encrypted),
        discovery_url=p.discovery_url,
        authorization_url=p.authorization_url,
        token_url=p.token_url,
        userinfo_url=p.userinfo_url,
        jwks_url=p.jwks_url,
        scopes=p.scopes,
        claim_mapping=ClaimMappingSchema(**(p.claim_mapping or {})),
        auto_provision=p.auto_provision,
        enabled=p.enabled,
    )


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("", response_model=list[OidcProviderListItem])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(OidcProvider).order_by(OidcProvider.name))
    providers = result.scalars().all()
    return [OidcProviderListItem(id=str(p.id), slug=p.slug, name=p.name, provider_type=p.provider_type, enabled=p.enabled) for p in providers]


@router.post("", response_model=OidcProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: OidcProviderCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if body.provider_type not in ("keycloak", "azure_entra", "generic_oidc"):
        raise HTTPException(status_code=400, detail="provider_type must be keycloak, azure_entra, or generic_oidc")

    slug = await _unique_slug(_slugify(body.name), db)
    encrypted_secret = ""
    if body.client_secret:
        encrypted_secret = _get_fernet().encrypt(body.client_secret.encode()).decode()

    provider = OidcProvider(
        slug=slug,
        name=body.name,
        provider_type=body.provider_type,
        client_id=body.client_id,
        client_secret_encrypted=encrypted_secret,
        discovery_url=body.discovery_url,
        authorization_url=body.authorization_url,
        token_url=body.token_url,
        userinfo_url=body.userinfo_url,
        jwks_url=body.jwks_url,
        scopes=body.scopes,
        claim_mapping=body.claim_mapping.model_dump(),
        auto_provision=body.auto_provision,
        enabled=body.enabled,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return _to_out(provider)


@router.get("/{provider_id}", response_model=OidcProviderOut)
async def get_provider(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(OidcProvider).where(OidcProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _to_out(provider)


@router.put("/{provider_id}", response_model=OidcProviderOut)
async def update_provider(
    provider_id: uuid.UUID,
    body: OidcProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(OidcProvider).where(OidcProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    if body.name is not None:
        provider.name = body.name
        provider.slug = await _unique_slug(_slugify(body.name), db, exclude_id=provider.id)
    if body.provider_type is not None:
        provider.provider_type = body.provider_type
    if body.client_id is not None:
        provider.client_id = body.client_id
    if body.client_secret is not None:
        provider.client_secret_encrypted = _get_fernet().encrypt(body.client_secret.encode()).decode() if body.client_secret else ""
    if body.discovery_url is not None:
        provider.discovery_url = body.discovery_url
    if body.authorization_url is not None:
        provider.authorization_url = body.authorization_url
    if body.token_url is not None:
        provider.token_url = body.token_url
    if body.userinfo_url is not None:
        provider.userinfo_url = body.userinfo_url
    if body.jwks_url is not None:
        provider.jwks_url = body.jwks_url
    if body.scopes is not None:
        provider.scopes = body.scopes
    if body.claim_mapping is not None:
        provider.claim_mapping = body.claim_mapping.model_dump()
    if body.auto_provision is not None:
        provider.auto_provision = body.auto_provision
    if body.enabled is not None:
        provider.enabled = body.enabled

    await db.commit()
    await db.refresh(provider)
    return _to_out(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(OidcProvider).where(OidcProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")

    await db.execute(
        User.__table__.update()
        .where(User.oidc_provider_id == provider_id)
        .values(oidc_provider_id=None)
    )
    await db.delete(provider)
    await db.commit()


@router.post("/{provider_id}/discover", response_model=DiscoverResponse)
async def discover_provider(
    provider_id: uuid.UUID,
    body: DiscoverRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(OidcProvider).where(OidcProvider.id == provider_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    try:
        disc = await oidc_service.discover(body.discovery_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Discovery failed: {e}")
    return DiscoverResponse(
        authorization_endpoint=disc.authorization_endpoint,
        token_endpoint=disc.token_endpoint,
        userinfo_endpoint=disc.userinfo_endpoint,
        jwks_uri=disc.jwks_uri,
        issuer=disc.issuer,
    )


@router.post("/discover", response_model=DiscoverResponse)
async def discover_new(
    body: DiscoverRequest,
    _admin: User = Depends(require_admin),
):
    """Discover endpoints before a provider is created."""
    try:
        disc = await oidc_service.discover(body.discovery_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Discovery failed: {e}")
    return DiscoverResponse(
        authorization_endpoint=disc.authorization_endpoint,
        token_endpoint=disc.token_endpoint,
        userinfo_endpoint=disc.userinfo_endpoint,
        jwks_uri=disc.jwks_uri,
        issuer=disc.issuer,
    )


@router.post("/{provider_id}/test")
async def test_provider(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(OidcProvider).where(OidcProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    results = await oidc_service.test_connectivity(provider)
    return results
