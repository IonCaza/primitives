import io
import json
import base64
import secrets
import logging

import bcrypt
import pyotp
import qrcode
import redis.asyncio as aioredis

from app.config import settings
from app.services.encryption import _get_fernet

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = 300  # 5 minutes
OTP_COOLDOWN_SECONDS = 60
RECOVERY_CODE_COUNT = 10

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


# ---------- TOTP ----------

def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_provisioning_uri(secret: str, email: str, issuer: str = "MyApp") -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def generate_qr_code_base64(uri: str) -> str:
    img = qrcode.make(uri, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def encrypt_totp_secret(secret: str) -> str:
    return _get_fernet().encrypt(secret.encode()).decode()


def decrypt_totp_secret(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


# ---------- Email OTP ----------

def generate_email_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def check_otp_cooldown(user_id: str) -> int:
    """Return remaining cooldown seconds, or 0 if the user can request a new OTP."""
    r = _get_redis()
    ttl = await r.ttl(f"mfa:otp_cooldown:{user_id}")
    return max(ttl, 0)


async def store_email_otp(user_id: str, code: str) -> None:
    r = _get_redis()
    key = f"mfa:email_otp:{user_id}"
    hashed = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
    await r.set(key, hashed, ex=OTP_TTL_SECONDS)
    await r.set(f"mfa:otp_cooldown:{user_id}", "1", ex=OTP_COOLDOWN_SECONDS)


async def verify_email_otp(user_id: str, code: str) -> bool:
    r = _get_redis()
    key = f"mfa:email_otp:{user_id}"
    stored = await r.get(key)
    if stored is None:
        return False
    if bcrypt.checkpw(code.encode(), stored.encode()):
        await r.delete(key)
        return True
    return False


# ---------- Recovery codes ----------

def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    return [secrets.token_hex(4).upper() for _ in range(count)]


def hash_recovery_codes(codes: list[str]) -> str:
    """Return Fernet-encrypted JSON of bcrypt hashes."""
    hashed = [bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode() for c in codes]
    payload = json.dumps(hashed)
    return _get_fernet().encrypt(payload.encode()).decode()


def verify_recovery_code(encrypted_codes: str, code: str) -> tuple[bool, str]:
    """Check a recovery code and return (valid, updated_encrypted_codes).

    A used code is removed from the list.
    """
    try:
        payload = _get_fernet().decrypt(encrypted_codes.encode()).decode()
        hashed_list: list[str] = json.loads(payload)
    except Exception:
        return False, encrypted_codes

    for i, h in enumerate(hashed_list):
        if bcrypt.checkpw(code.encode(), h.encode()):
            hashed_list.pop(i)
            updated = json.dumps(hashed_list)
            new_encrypted = _get_fernet().encrypt(updated.encode()).decode()
            return True, new_encrypted
    return False, encrypted_codes
