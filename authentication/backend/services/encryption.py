import base64
import hashlib
from enum import Enum

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings


class KeyType(str, Enum):
    ED25519 = "ed25519"
    RSA = "rsa"


def _get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def generate_keypair(key_type: KeyType = KeyType.ED25519, rsa_bits: int = 4096) -> tuple[str, str, str, str]:
    """Returns (public_key_openssh, encrypted_private_key, fingerprint, key_type)."""
    if key_type == KeyType.RSA:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=rsa_bits)
    else:
        private_key = Ed25519PrivateKey.generate()

    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    )
    private_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    )
    public_key_str = public_bytes.decode()
    fingerprint = hashlib.sha256(public_bytes).hexdigest()[:16]

    fernet = _get_fernet()
    encrypted_private = fernet.encrypt(private_bytes).decode()

    return public_key_str, encrypted_private, fingerprint, key_type.value


def decrypt_private_key(encrypted: str) -> bytes:
    fernet = _get_fernet()
    return fernet.decrypt(encrypted.encode())
