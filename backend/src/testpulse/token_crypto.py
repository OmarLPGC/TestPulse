import base64
import secrets
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_token(token: str, encoded_key: str) -> str:
    key = _decode_key(encoded_key)
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, token.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_token(ciphertext: str, encoded_key: str) -> str:
    key = _decode_key(encoded_key)
    try:
        decoded = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        if len(decoded) < 29:
            raise ValueError("Encrypted token is too short.")
        return AESGCM(key).decrypt(decoded[:12], decoded[12:], None).decode("utf-8")
    except (InvalidTag, UnicodeEncodeError, ValueError) as exc:
        raise ValueError("Stored GitHub credential could not be decrypted.") from exc


def _decode_key(encoded_key: Optional[str]) -> bytes:
    if not encoded_key:
        raise ValueError("GitHub token encryption is not configured.")
    try:
        encoded = encoded_key.encode("ascii")
        key = base64.b64decode(
            encoded + b"=" * (-len(encoded) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, ValueError) as exc:
        raise ValueError("GitHub token encryption key is invalid.") from exc
    if len(key) != 32:
        raise ValueError("GitHub token encryption key must encode 32 bytes.")
    return key
