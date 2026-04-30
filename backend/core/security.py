import hashlib
import logging
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from backend.config import settings

logger = logging.getLogger(__name__)

# Identity claims for issued tokens. Both must be present and verified at decode.
JWT_ISSUER = "rwa-platform"
JWT_AUDIENCE = "rwa-platform-api"


def _prepare_password(password: str) -> bytes:
    """SHA-256 the UTF-8 password before bcrypt to avoid silent 72-byte truncation.

    The pre-hash is base64-encoded so the result fits within bcrypt's 72-byte
    input ceiling regardless of the original password length.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    import base64
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(_prepare_password(password), salt)
    return hashed.decode("utf-8")


get_password_hash = hash_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare_password(plain_password), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict[str, str | int], expires_delta: timedelta | None = None) -> str:
    allowed_keys = {"sub", "role", "org_id"}
    filtered_data: dict[str, str | int] = {k: v for k, v in data.items() if k in allowed_keys}

    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))

    filtered_data["exp"] = int(expire.timestamp())
    filtered_data["iat"] = int(now.timestamp())
    filtered_data["nbf"] = int(now.timestamp())
    filtered_data["iss"] = JWT_ISSUER
    filtered_data["aud"] = JWT_AUDIENCE

    return jwt.encode(filtered_data, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, str | int]:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "nbf", "sub", "iss", "aud"]},
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired token.") from exc
