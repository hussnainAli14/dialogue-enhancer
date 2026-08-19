"""Fernet symmetric encryption for platform tokens.

The key is read from TOKEN_ENCRYPTION_KEY. Tokens are always encrypted
before they touch the database and decrypted only in memory for API calls.
Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from functools import lru_cache

from app.config import settings


@lru_cache
def _fernet():
    from cryptography.fernet import Fernet

    key = settings.TOKEN_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is not set. Generate one with "
            "Fernet.generate_key() and add it to your .env."
        )
    # Accept the key as str; Fernet needs bytes.
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plaintext: str | None) -> str | None:
    """Encrypt a token. None/empty passes through as None."""
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str | None) -> str | None:
    """Decrypt a token. None/empty passes through as None. Returns None if
    the value cannot be decrypted (e.g. key rotated) rather than raising."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return None
