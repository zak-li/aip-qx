from typing import Annotated
from collections.abc import AsyncGenerator, Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.database import get_session
from backend.core.redis_client import get_redis
from backend.core.security import decode_token
from backend.exceptions import InsufficientPermissionsError
from backend.fabric_client.network import FabricClient
from backend.fabric_client.wallet import FabricWallet
from backend.features.auth.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# MSP ID → Fabric wallet identity label.
# Strict mapping: any user with a missing or unmapped MSP is rejected — never
# silently downgraded to a privileged identity.
_MSP_TO_IDENTITY: dict[str, str] = {
    "BNPParibasMSP": "Admin@bnpparibas",
    "AMFRegulateurMSP": "Admin@amf-regulateur",
}


def resolve_identity(user: User) -> str:
    """Return the Fabric wallet identity label for a given user.

    Raises HTTP 403 if the user has no MSP or an MSP that is not explicitly
    mapped to a Fabric identity — refuses to fall back to any default.
    """
    if not user.msp_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no MSP assigned — cannot sign Fabric transactions.",
        )
    identity = _MSP_TO_IDENTITY.get(user.msp_id)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"MSP '{user.msp_id}' is not mapped to a Fabric identity.",
        )
    return identity


_fabric_client_instance: FabricClient | None = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


def get_fabric() -> FabricClient:
    global _fabric_client_instance
    if _fabric_client_instance is None:
        wallet = FabricWallet(settings)
        _fabric_client_instance = FabricClient(settings, wallet)
    return _fabric_client_instance


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
    redis_conn: Redis = Depends(get_redis),
) -> User:
    is_blacklisted = await redis_conn.get(f"blacklist:{token}")
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked.",
        )

    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
        )

    try:
        user_uuid = UUID(str(user_id_str))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject claim.",
        ) from exc

    iat = payload.get("iat", 0)
    last_logout_raw = await redis_conn.get(f"token:invalidated:{user_id_str}")
    if last_logout_raw and int(iat) <= int(last_logout_raw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated, please log in again.",
        )

    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    if user.is_locked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is locked.")

    return user


def require_role(*roles: str) -> Callable[..., User]:
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise InsufficientPermissionsError(required_role=" | ".join(roles))
        return current_user

    return role_checker
