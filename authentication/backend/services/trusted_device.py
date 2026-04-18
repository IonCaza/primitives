"""Trusted-device token service used by "Remember me for 30 days" on MFA.

When a user ticks "Remember this device for 30 days" during MFA verification,
the server generates a random 32-byte url-safe token, stores only its SHA-256
hash in the ``trusted_devices`` table, and returns the raw token to the client.
The client persists the raw token in ``localStorage`` on that device only.

On a future login for the same user, the client sends the raw token back in the
login request; if it hashes to a non-expired row belonging to that user, the
MFA challenge is skipped for that login and normal access/refresh tokens are
issued directly.

Security notes:
    - The raw token is never persisted server-side, so a database dump does not
      leak usable trust tokens.
    - Trust tokens are bound to a specific user_id; a token issued to user A
      will never let someone log in as user B, even if the same browser is
      re-used by a different user.
    - Trusted devices are revoked on password change, MFA disable, MFA reset,
      and any explicit user/admin action.
    - SHA-256 is used instead of bcrypt because the raw token already has
      >=256 bits of entropy, so a slow hash buys nothing useful here.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trusted_device import TrustedDevice

TRUSTED_DEVICE_TTL_DAYS = 30
_MAX_UA_LEN = 512
_MAX_IP_LEN = 64


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


async def create_trusted_device(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
    device_label: str | None = None,
) -> str:
    """Persist a new trusted-device row and return the raw token (shown once)."""
    raw = _generate_raw_token()
    now = datetime.now(timezone.utc)
    device = TrustedDevice(
        user_id=user_id,
        token_hash=_hash_token(raw),
        device_label=device_label,
        user_agent=(user_agent[:_MAX_UA_LEN] if user_agent else None),
        ip_address=(ip_address[:_MAX_IP_LEN] if ip_address else None),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=TRUSTED_DEVICE_TTL_DAYS),
    )
    db.add(device)
    await db.commit()
    return raw


async def verify_trusted_device(
    db: AsyncSession,
    user_id: uuid.UUID,
    raw_token: str | None,
) -> bool:
    """Return True if raw_token matches a non-expired trusted device for user_id.

    On success, ``last_used_at`` is bumped to now.
    """
    if not raw_token:
        return False
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TrustedDevice).where(
            TrustedDevice.token_hash == _hash_token(raw_token),
            TrustedDevice.user_id == user_id,
            TrustedDevice.expires_at > now,
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        return False
    device.last_used_at = now
    await db.commit()
    return True


async def list_user_trusted_devices(db: AsyncSession, user_id: uuid.UUID) -> list[TrustedDevice]:
    """Return all non-expired trusted devices for a user, newest first."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(TrustedDevice)
        .where(TrustedDevice.user_id == user_id, TrustedDevice.expires_at > now)
        .order_by(TrustedDevice.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_trusted_device(
    db: AsyncSession,
    user_id: uuid.UUID,
    device_id: uuid.UUID,
) -> bool:
    """Delete a single trusted device owned by the user. Returns True if found."""
    result = await db.execute(
        delete(TrustedDevice).where(
            TrustedDevice.id == device_id,
            TrustedDevice.user_id == user_id,
        )
    )
    await db.commit()
    return (result.rowcount or 0) > 0


async def revoke_all_trusted_devices(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Delete all trusted devices for a user. Returns the count deleted.

    Must be called on any security-sensitive change: password change, MFA disable,
    admin MFA reset, admin user deactivate, etc.
    """
    result = await db.execute(
        delete(TrustedDevice).where(TrustedDevice.user_id == user_id)
    )
    await db.commit()
    return result.rowcount or 0
