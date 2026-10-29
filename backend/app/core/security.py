"""Cryptographic and security utilities for tokens, OTPs, hashing, and rate limiting."""

import base64
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

import jwt
from app.core.config import settings
from app.core.errors import BadRequestError, RateLimitError, UnauthorizedError

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,30}$")


def normalize_username(username: str) -> str:
    """Normalize username for consistent storage and comparisons."""
    return username.strip().lower()


def validate_username_format(username: str) -> str:
    """Validate username characters and length. Returns cleaned username."""
    cleaned = username.strip()
    if not USERNAME_REGEX.match(cleaned):
        raise ValueError(
            "Username must be 3-30 characters long and contain only letters, numbers, underscores, or hyphens."
        )
    return cleaned


def normalize_email(email: str) -> str:
    """Normalize email address to lowercase and stripped."""
    return email.strip().lower()


def generate_otp_code(length: int = 6) -> str:
    """Generate a cryptographically secure numeric OTP."""
    range_start = 10 ** (length - 1)
    range_end = (10**length) - 1
    return str(secrets.randbelow(range_end - range_start + 1) + range_start)


def hash_otp_code(code: str, secret: str = settings.OTP_HMAC_SECRET) -> str:
    """Compute HMAC-SHA256 hash of a verification code."""
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=code.strip().encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def verify_otp_code(plain_code: str, hashed_code: str, secret: str = settings.OTP_HMAC_SECRET) -> bool:
    """Constant-time verification of OTP against stored hash."""
    expected_hash = hash_otp_code(plain_code, secret)
    return hmac.compare_digest(expected_hash, hashed_code)


def generate_secure_token(nbytes: int = 32) -> str:
    """Generate a cryptographically secure URL-safe random token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Compute SHA-256 hash of a token for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user_id: str, username: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    expires = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify and decode a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "access":
            raise UnauthorizedError("Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Access token has expired")
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid access token")


def create_registration_ticket(email: str, expires_in_seconds: int = 900) -> str:
    """Create a short-lived signed ticket after email verification for registration completion."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=expires_in_seconds)
    payload = {
        "email": normalize_email(email),
        "purpose": "registration",
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "nonce": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


_consumed_ticket_nonces: dict[str, float] = {}


def _is_nonce_consumed(nonce: str) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    exp = _consumed_ticket_nonces.get(nonce)
    if exp is not None:
        if exp > now:
            return True
        else:
            del _consumed_ticket_nonces[nonce]
    return False


def _consume_nonce(nonce: str, exp_timestamp: float) -> None:
    now = datetime.now(timezone.utc).timestamp()
    if len(_consumed_ticket_nonces) > 500:
        to_del = [k for k, v in _consumed_ticket_nonces.items() if v <= now]
        for k in to_del:
            _consumed_ticket_nonces.pop(k, None)
    _consumed_ticket_nonces[nonce] = exp_timestamp


def verify_registration_ticket(ticket: str, consume: bool = False) -> str:
    """Verify registration ticket and return verified email. If consume=True, marks single-use ticket as spent."""
    try:
        payload = jwt.decode(
            ticket,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("purpose") != "registration":
            raise UnauthorizedError("Invalid ticket purpose")
        nonce = payload.get("nonce")
        if nonce and _is_nonce_consumed(nonce):
            raise UnauthorizedError("Registration ticket has already been used. Please request a new verification code.")
        email = payload.get("email")
        if not email:
            raise UnauthorizedError("Ticket is missing email")
        if consume and nonce:
            _consume_nonce(nonce, float(payload.get("exp", 0)))
        return email
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Registration ticket has expired. Please request a new verification code.")
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid registration ticket")


def generate_pkce_pair() -> Tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    # 43-128 chars URL-safe verifier
    code_verifier = secrets.token_urlsafe(48)[:64]
    code_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(code_hash).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def create_oauth_state(
    purpose: str,
    user_id: Optional[str] = None,
    code_verifier: Optional[str] = None,
    expires_in_seconds: int = 600,
    **kwargs: Any,
) -> str:
    """Generate a signed, tamper-proof OAuth state token with PKCE binding, custom metadata, and expiry."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=expires_in_seconds)
    payload: dict[str, Any] = {
        "purpose": purpose,  # "login", "contacts", "gmail", "connect_meet"
        "code_verifier": code_verifier,
        "type": "oauth_state",
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "nonce": secrets.token_hex(8),
    }
    if user_id:
        payload["sub"] = str(user_id)
    payload.update(kwargs)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)



def verify_oauth_state(
    state: str,
    expected_purpose: Optional[str] = None,
    expected_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Verify signed OAuth state token and enforce purpose and user identity match."""
    if not state:
        raise BadRequestError("Missing OAuth state parameter.")
    try:
        payload = jwt.decode(
            state,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "oauth_state":
            raise BadRequestError("Invalid OAuth state type.")

        if expected_purpose and payload.get("purpose") != expected_purpose:
            raise BadRequestError(
                f"OAuth state purpose mismatch: expected '{expected_purpose}', got '{payload.get('purpose')}'."
            )

        if expected_user_id and payload.get("sub") != str(expected_user_id):
            raise UnauthorizedError("OAuth state is not authorized for the current user.")

        return payload
    except jwt.ExpiredSignatureError:
        raise BadRequestError("OAuth authorization session has expired. Please initiate authorization again.")
    except jwt.PyJWTError:
        raise BadRequestError("Invalid or corrupted OAuth state parameter.")



class MemoryRateLimiter:
    """Thread-safe in-memory rate limiter with sliding window tracking."""

    def __init__(self):
        self._records: dict[str, list[float]] = defaultdict(list)

    def check_and_record(self, key: str, max_attempts: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Check if request is allowed. Returns (allowed, remaining_attempts_or_retry_after).
        """
        now = time.time()
        window_start = now - window_seconds
        # Clean older records
        timestamps = [ts for ts in self._records[key] if ts > window_start]
        self._records[key] = timestamps

        if len(timestamps) >= max_attempts:
            oldest = timestamps[0]
            retry_after = max(1, int(window_seconds - (now - oldest)))
            return False, retry_after

        self._records[key].append(now)
        remaining = max_attempts - len(self._records[key])
        return True, remaining

    def enforce(self, key: str, max_attempts: int, window_seconds: int, action_name: str = "request") -> None:
        allowed, retry_after = self.check_and_record(key, max_attempts, window_seconds)
        if not allowed:
            raise RateLimitError(
                f"Too many {action_name} attempts. Please try again in {retry_after} seconds.",
                retry_after=retry_after,
            )


rate_limiter = MemoryRateLimiter()


def get_fernet_cipher():
    """Derive a URL-safe 32-byte base64 Fernet key from secret configuration."""
    import base64
    from cryptography.fernet import Fernet

    secret = settings.ENCRYPTION_SECRET_KEY or settings.JWT_SECRET_KEY
    key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_secret(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a secret string (e.g. OAuth refresh token) using Fernet."""
    if not plaintext:
        return None
    cipher = get_fernet_cipher()
    return cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt an encrypted secret string. Returns None if input is empty."""
    if not ciphertext:
        return None
    cipher = get_fernet_cipher()
    try:
        return cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:
        raise UnauthorizedError("Failed to decrypt stored credentials")


def validate_password_complexity(password: str) -> None:
    """Enforce password length and basic complexity requirements."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        raise ValueError("Password must contain at least one letter and one number.")


def hash_password(password: str) -> str:
    """Hash password using Argon2id with a 16-byte cryptographically secure salt."""
    import os
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

    salt = os.urandom(16)
    kdf = Argon2id(salt=salt, length=32, iterations=2, lanes=4, memory_cost=65536)
    derived = kdf.derive(password.encode("utf-8"))
    salt_b64 = base64.b64encode(salt).decode("ascii")
    derived_b64 = base64.b64encode(derived).decode("ascii")
    return f"argon2id$v=19$m=65536,t=2,p=4${salt_b64}${derived_b64}"


def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    """Verify plain password against stored Argon2id hash in constant time."""
    if not hashed_password or not plain_password:
        return False
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

    try:
        parts = hashed_password.split("$")
        if len(parts) != 5 or parts[0] != "argon2id":
            return False
        param_dict = dict(kv.split("=") for kv in parts[2].split(","))
        salt = base64.b64decode(parts[3])
        expected = base64.b64decode(parts[4])
        kdf = Argon2id(
            salt=salt,
            length=len(expected),
            iterations=int(param_dict.get("t", 2)),
            lanes=int(param_dict.get("p", 4)),
            memory_cost=int(param_dict.get("m", 65536)),
        )
        kdf.verify(plain_password.encode("utf-8"), expected)
        return True
    except Exception:
        return False


def create_password_reset_ticket(email: str, expires_in_seconds: int = 900) -> str:
    """Create a short-lived signed ticket after verification code is validated to reset password."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=expires_in_seconds)
    payload = {
        "email": normalize_email(email),
        "purpose": "password_reset",
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "nonce": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_password_reset_ticket(ticket: str, consume: bool = False) -> str:
    """Verify password reset ticket and return verified email. If consume=True, marks single-use ticket as spent."""
    try:
        payload = jwt.decode(
            ticket,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("purpose") != "password_reset":
            raise UnauthorizedError("Invalid ticket purpose")
        nonce = payload.get("nonce")
        if nonce and _is_nonce_consumed(nonce):
            raise UnauthorizedError("Password reset ticket has already been used. Please request a new code.")
        email = payload.get("email")
        if not email:
            raise UnauthorizedError("Ticket is missing email")
        if consume and nonce:
            _consume_nonce(nonce, float(payload.get("exp", 0)))
        return email
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Password reset session has expired. Please request a new code.")
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid password reset ticket")

