import threading
from collections.abc import Callable

import grpc
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.core.database import get_session
from core.exceptions import InsufficientPermissionsError
from core.fabric_client.network import FabricClient
from core.fabric_client.wallet import FabricWallet
from core.features.auth.models import User

# MSP ID → Fabric wallet identity label.
_MSP_TO_IDENTITY: dict[str, str] = {
    "BANK01MSP": "admin@bank01",
    "REG01MSP": "admin@reg01-regulateur",
}


def resolve_identity_from_payload(payload: dict) -> str:
    msp_id = payload.get("msp_id")
    if not msp_id:
        raise grpc.RpcError(grpc.StatusCode.PERMISSION_DENIED)  # type: ignore[attr-defined]
    identity = _MSP_TO_IDENTITY.get(msp_id)
    if identity is None:
        raise grpc.RpcError(grpc.StatusCode.PERMISSION_DENIED)  # type: ignore[attr-defined]
    return identity


def resolve_identity(user: User) -> str:
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
_fabric_client_lock = threading.Lock()


async def get_db():
    async for session in get_session():
        yield session


def get_fabric() -> FabricClient:
    global _fabric_client_instance
    if _fabric_client_instance is None:
        with _fabric_client_lock:
            if _fabric_client_instance is None:
                wallet = FabricWallet(settings)
                _fabric_client_instance = FabricClient(settings, wallet)
    return _fabric_client_instance


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the Keycloak subject from request state to a local User record."""
    keycloak_sub: str | None = getattr(request.state, "keycloak_sub", None)
    if not keycloak_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stmt = select(User).where(
        User.keycloak_sub == keycloak_sub,
        User.is_active.is_(True),
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )
    return user


def require_role(*roles: str) -> Callable[..., User]:
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise InsufficientPermissionsError(required_role=" | ".join(roles))
        return current_user

    return role_checker
