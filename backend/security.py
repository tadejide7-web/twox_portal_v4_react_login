"""Password hashing, signed tokens and login throttling. Standard library only."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

ITERATIONS = 260_000
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters)).hex()
        return hmac.compare_digest(test, digest)
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(user_id: int, secret: str, ttl_seconds: int, now: Optional[float] = None) -> str:
    payload = {"sub": user_id, "exp": int((now if now is not None else time.time()) + ttl_seconds)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str, secret: str, now: Optional[float] = None) -> Optional[int]:
    """Return the user id if the token is genuine and unexpired, else None."""
    try:
        body, sig = token.split(".")
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if payload["exp"] < (now if now is not None else time.time()):
            return None
        return int(payload["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


class LoginThrottle:
    """Locks a username out for a while after repeated failed logins (in memory)."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 900):
        self.max_failures, self.window = max_failures, window_seconds
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key.lower(), []) if now - t < self.window]
        self._failures[key.lower()] = recent
        return recent

    def locked(self, key: str, now: Optional[float] = None) -> bool:
        return len(self._recent(key, now if now is not None else time.time())) >= self.max_failures

    def fail(self, key: str, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        self._recent(key, now).append(now)

    def reset(self, key: str) -> None:
        self._failures.pop(key.lower(), None)
