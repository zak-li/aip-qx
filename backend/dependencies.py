from typing import Annotated ,Callable ,AsyncGenerator 
from uuid import UUID 

from fastapi import Depends ,HTTPException ,status 
from fastapi .security import OAuth2PasswordBearer 
from sqlalchemy import select 
from sqlalchemy .ext .asyncio import AsyncSession 
from redis .asyncio import Redis 

from backend .config import settings 
from backend .core .database import get_session 
from backend .core .redis_client import get_redis 
from backend .core .security import decode_token 
from backend .fabric_client .network import FabricClient 
from backend .fabric_client .wallet import FabricWallet 
from backend.features.auth.models import User
from backend .exceptions import InsufficientPermissionsError 

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# MSP ID → Fabric wallet identity label.
# Falls back to the BNP admin so unknown actors never gain regulator-level signing rights.
_MSP_TO_IDENTITY: dict[str, str] = {
    "BNPParibasMSP": "Admin@bnpparibas",
    "AMFRegulateurMSP": "Admin@amf-regulateur",
}
_DEFAULT_IDENTITY = "Admin@bnpparibas"


def resolve_identity(user: User) -> str:
    """Return the Fabric wallet identity label for a given user."""
    return _MSP_TO_IDENTITY.get(user.msp_id or "", _DEFAULT_IDENTITY)


_fabric_client_instance: FabricClient | None = None

async def get_db ()->AsyncGenerator [AsyncSession ,None ]:
    async for session in get_session ():
        yield session 

def get_fabric ()->FabricClient :
    global _fabric_client_instance 
    if _fabric_client_instance is None :
        wallet =FabricWallet (settings )
        _fabric_client_instance =FabricClient (settings ,wallet )
    return _fabric_client_instance 

async def get_current_user (
token :Annotated [str ,Depends (oauth2_scheme )],
db :AsyncSession =Depends (get_db ),
redis_conn :Redis =Depends (get_redis )
)->User :
    is_blacklisted =await redis_conn .get (f"blacklist:{token }")
    if is_blacklisted :
        raise HTTPException (status_code =status .HTTP_401_UNAUTHORIZED ,detail ="Token has been revoked.")

    try :
        payload =decode_token (token )
    except ValueError as exc :
        raise HTTPException (status_code =status .HTTP_401_UNAUTHORIZED ,detail ="Invalid token.")from exc

    user_id_str =payload .get ("sub")
    if not user_id_str :
        raise HTTPException (status_code =status .HTTP_401_UNAUTHORIZED ,detail ="Token missing subject claim.")

    stmt =select (User ).where (User .id ==UUID (str (user_id_str )))
    result =await db .execute (stmt )
    user =result .scalar_one_or_none ()

    if not user :
        raise HTTPException (status_code =status .HTTP_401_UNAUTHORIZED ,detail ="User not found.")

    if user .is_locked :
        raise HTTPException (status_code =status .HTTP_403_FORBIDDEN ,detail ="Account is locked.")

    return user 

def require_role (*roles :str )->Callable [...,User ]:
    async def role_checker (current_user :User =Depends (get_current_user ))->User :
        if current_user .role not in roles :
            raise InsufficientPermissionsError (required_role =" | ".join (roles ))
        return current_user 
    return role_checker 
