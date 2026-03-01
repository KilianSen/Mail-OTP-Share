"""
Encryption helpers for storing sensitive credentials.
Uses Fernet symmetric encryption with the APP_SECRET_KEY.
"""
import base64
import hashlib
from cryptography.fernet import Fernet
from app.config import settings


def _get_fernet() -> Fernet:
    # Derive a 32-byte key from the secret
    key = hashlib.sha256(settings.APP_SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""
