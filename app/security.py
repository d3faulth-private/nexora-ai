from __future__ import annotations

import secrets
import time
from collections import defaultdict

import bcrypt

from .config import get_settings


_login_failures: dict[str, list[float]] = defaultdict(list)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_valid(expected: str | None, supplied: str | None) -> bool:
    if not expected or not supplied:
        return False
    return secrets.compare_digest(str(expected), str(supplied))


def login_key(client_ip: str, email: str) -> str:
    return client_ip + "|" + email.strip().lower()


def login_blocked(key: str) -> bool:
    settings = get_settings()
    now = time.time()
    cutoff = now - settings.login_rate_limit_window_seconds
    _login_failures[key] = [stamp for stamp in _login_failures[key] if stamp >= cutoff]
    return len(_login_failures[key]) >= settings.login_rate_limit_attempts


def record_login_failure(key: str) -> None:
    _login_failures[key].append(time.time())


def clear_login_failures(key: str) -> None:
    _login_failures.pop(key, None)
