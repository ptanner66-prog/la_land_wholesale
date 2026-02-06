"""Authentication utilities: JWT tokens and password hashing.

Uses a pure-Python HMAC-SHA256 JWT implementation to avoid cryptography
library issues. HS256 only uses stdlib's hmac module.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.config import get_settings

SETTINGS = get_settings()


# ---------------------------------------------------------------------------
# Pure-Python HS256 JWT (no external library needed)
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _jwt_encode(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":"), default=str).encode()),
    ]
    signing_input = f"{segments[0]}.{segments[1]}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    segments.append(_b64url_encode(sig))
    return ".".join(segments)


def _jwt_decode(token: str, secret: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        signing_input = f"{parts[0]}.{parts[1]}"
        expected_sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        actual_sig = _b64url_decode(parts[2])

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload = json.loads(_b64url_decode(parts[1]))

        # Check expiration
        exp = payload.get("exp")
        if exp is not None:
            if isinstance(exp, str):
                exp_dt = datetime.fromisoformat(exp)
                if exp_dt.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    return None
            elif isinstance(exp, (int, float)):
                if exp < time.time():
                    return None

        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Password Hashing (bcrypt via passlib)
# ---------------------------------------------------------------------------

def _try_passlib() -> bool:
    """Try to initialize passlib with bcrypt."""
    try:
        from passlib.context import CryptContext
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        # Smoke test to verify the backend works
        h = ctx.hash("test")
        ctx.verify("test", h)
        return True
    except Exception:
        return False


if _try_passlib():
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(password: str) -> str:
        """Hash a password with bcrypt."""
        return _pwd_context.hash(password)

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return _pwd_context.verify(plain_password, hashed_password)

else:
    # Fallback: PBKDF2-SHA256 with high iterations (secure, pure-Python)
    import os as _os

    def hash_password(password: str) -> str:
        """Hash a password with PBKDF2-SHA256."""
        salt = _os.urandom(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260000)
        return f"pbkdf2${salt.hex()}${dk.hex()}"

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its PBKDF2 hash."""
        try:
            _, salt_hex, expected_hex = hashed_password.split("$", 2)
            salt = bytes.fromhex(salt_hex)
            dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt, 260000)
            return hmac.compare_digest(dk.hex(), expected_hex)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Token Creation/Decoding
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, email: str, role: str) -> str:
    """Create a JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=SETTINGS.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    return _jwt_encode(payload, SETTINGS.jwt_secret_key)


def create_refresh_token() -> tuple[str, str]:
    """
    Create a refresh token.

    Returns:
        Tuple of (raw_token, token_hash) — raw_token goes to client,
        token_hash is stored server-side.
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT access token.

    Returns:
        Token payload dict, or None if invalid/expired.
    """
    payload = _jwt_decode(token, SETTINGS.jwt_secret_key)
    if payload is None:
        return None
    if payload.get("type") != "access":
        return None
    return payload


def hash_refresh_token(raw_token: str) -> str:
    """Hash a raw refresh token for database lookup."""
    return hashlib.sha256(raw_token.encode()).hexdigest()
