from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class VaultUnavailable(RuntimeError):
    pass


def _fernet() -> Fernet:
    raw = get_settings().connector_encryption_key.strip()
    if not raw:
        raise VaultUnavailable(
            "CONNECTOR_ENCRYPTION_KEY is required before storing real connector credentials."
        )

    try:
        if len(raw) == 44:
            return Fernet(raw.encode("utf-8"))
    except Exception:
        pass

    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_json(value: dict) -> str:
    data = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return _fernet().encrypt(data).decode("utf-8")


def decrypt_json(blob: str) -> dict:
    try:
        decoded = _fernet().decrypt(blob.encode("utf-8"))
        return json.loads(decoded.decode("utf-8"))
    except InvalidToken as exc:
        raise VaultUnavailable("Connector credential could not be decrypted.") from exc
