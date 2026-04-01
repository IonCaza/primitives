"""OIDC discovery, PKCE, token exchange, JWKS fetch, and ID-token validation."""

from __future__ import annotations

import hashlib
import base64
import json
import logging
import secrets
from dataclasses import dataclass

import httpx
import jwt
import redis.asyncio as aioredis
from jwt import PyJWKClient

from app.config import settings
from app.db.models.oidc_provider import OidcProvider

logger = logging.getLogger(__name__)

STATE_TTL_SECONDS = 600  # 10 min
JWKS_CACHE_TTL = 3600    # 1 hour

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@dataclass
class DiscoveryResult:
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None
    jwks_uri: str
    issuer: str


async def discover(discovery_url: str) -> DiscoveryResult:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(discovery_url)
        resp.raise_for_status()
        data = resp.json()
    return DiscoveryResult(
        authorization_endpoint=data["authorization_endpoint"],
        token_endpoint=data["token_endpoint"],
        userinfo_endpoint=data.get("userinfo_endpoint"),
        jwks_uri=data["jwks_uri"],
        issuer=data["issuer"],
    )


def build_discovery_url(provider_type: str, *, realm_url: str | None = None, tenant_id: str | None = None) -> str | None:
    if provider_type == "keycloak" and realm_url:
        return f"{realm_url.rstrip('/')}/.well-known/openid-configuration"
    if provider_type == "azure_entra" and tenant_id:
        return f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
    return None


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def _generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------

async def build_authorization_url(
    provider: OidcProvider,
    redirect_uri: str,
) -> tuple[str, str]:
    """Return (authorization_url, state). Stores state + verifier in Redis."""
    state = secrets.token_urlsafe(32)
    verifier = _generate_code_verifier()
    challenge = _generate_code_challenge(verifier)

    r = _get_redis()
    await r.setex(
        f"oidc_state:{state}",
        STATE_TTL_SECONDS,
        json.dumps({"code_verifier": verifier, "provider_id": str(provider.id)}),
    )

    params = {
        "client_id": provider.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": provider.scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = httpx.URL(provider.authorization_url, params=params)
    return str(url), state


# ---------------------------------------------------------------------------
# State validation
# ---------------------------------------------------------------------------

async def validate_state(state: str) -> dict | None:
    r = _get_redis()
    raw = await r.getdel(f"oidc_state:{state}")
    if raw is None:
        return None
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------

async def exchange_code(
    provider: OidcProvider,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict:
    from app.services.encryption import _get_fernet

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": provider.client_id,
        "code_verifier": code_verifier,
    }
    if provider.client_secret_encrypted:
        try:
            client_secret = _get_fernet().decrypt(provider.client_secret_encrypted.encode()).decode()
            data["client_secret"] = client_secret
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(provider.token_url, data=data)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# JWKS & ID-token validation
# ---------------------------------------------------------------------------

_jwk_clients: dict[str, PyJWKClient] = {}


def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    if jwks_url not in _jwk_clients:
        _jwk_clients[jwks_url] = PyJWKClient(jwks_url, cache_keys=True, lifespan=JWKS_CACHE_TTL)
    return _jwk_clients[jwks_url]


def validate_id_token(provider: OidcProvider, id_token: str) -> dict:
    jwk_client = _get_jwk_client(provider.jwks_url)
    signing_key = jwk_client.get_signing_key_from_jwt(id_token)
    return jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=provider.client_id,
        options={"verify_exp": True, "verify_aud": True},
    )


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

@dataclass
class UserClaims:
    subject: str
    email: str
    full_name: str | None
    groups: list[str]
    is_admin: bool


def extract_user_claims(provider: OidcProvider, claims: dict) -> UserClaims:
    mapping = provider.claim_mapping or {}
    email_key = mapping.get("email", "email")
    name_key = mapping.get("name", "name")
    groups_key = mapping.get("groups", "groups")
    admin_groups: list[str] = mapping.get("admin_groups", [])

    email = claims.get(email_key, "")
    full_name = claims.get(name_key)
    raw_groups = claims.get(groups_key, [])
    if isinstance(raw_groups, str):
        raw_groups = [raw_groups]

    is_admin = bool(admin_groups and any(g in admin_groups for g in raw_groups))

    return UserClaims(
        subject=claims["sub"],
        email=email,
        full_name=full_name,
        groups=raw_groups,
        is_admin=is_admin,
    )


# ---------------------------------------------------------------------------
# Connectivity test
# ---------------------------------------------------------------------------

async def test_connectivity(provider: OidcProvider) -> dict[str, bool | str]:
    results: dict[str, bool | str] = {}

    if provider.discovery_url:
        try:
            await discover(provider.discovery_url)
            results["discovery"] = True
        except Exception as e:
            results["discovery"] = False
            results["discovery_error"] = str(e)
    else:
        results["discovery"] = False
        results["discovery_error"] = "No discovery URL configured"

    if provider.jwks_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(provider.jwks_url)
                resp.raise_for_status()
            results["jwks"] = True
        except Exception as e:
            results["jwks"] = False
            results["jwks_error"] = str(e)
    else:
        results["jwks"] = False
        results["jwks_error"] = "No JWKS URL configured"

    return results
