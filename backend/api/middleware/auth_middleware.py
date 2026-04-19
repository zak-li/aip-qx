import re 
from typing import Awaitable ,Callable 
from fastapi import Request ,Response 
from fastapi .responses import JSONResponse 
from starlette .middleware .base import BaseHTTPMiddleware 

from backend .core .security import decode_token 
from backend .core .redis_client import get_redis 

EXCLUDED_PATHS = re.compile(
    r"^\/("
    r"api\/v1\/auth\/login"
    r"|health|metrics|docs|openapi\.json"
    r"|agent|assets|animations"
    r"|favicon\.svg|robots\.txt|site\.webmanifest"
    r"|$"
    r").*$"
)

class AuthMiddleware (BaseHTTPMiddleware ):
    
    async def dispatch (self ,request :Request ,call_next :Callable [[Request ],Awaitable [Response ]])->Response :

        path :str =request .url .path 
        if EXCLUDED_PATHS .match (path ):
            return await call_next (request )

        auth_header :str |None =request .headers .get ("Authorization")
        if not auth_header or not auth_header .startswith ("Bearer "):
            return JSONResponse (
            status_code =401 ,
            content ={"error":"Unauthorized","message":"Missing or malformed Authorization header. Expected: Bearer <token>."}
            )

        token :str =auth_header .split (" ")[1 ]

        try :
            redis_gen =get_redis ()
            redis_conn =await redis_gen .__anext__ ()
            is_blacklisted =await redis_conn .get (f"blacklist:{token }")

            payload =decode_token (token )
            user_id =payload .get ("sub")
            iat =payload .get ("iat",0 )

            last_logout_raw =await redis_conn .get (f"token:invalidated:{user_id }")
            if last_logout_raw :
                last_logout =int (last_logout_raw )
                if int (iat )<=last_logout :
                    is_blacklisted =True

            await redis_gen .aclose ()
        except ValueError as exc :
            return JSONResponse (status_code =401 ,content ={"error":"Unauthorized","message":str (exc )})
        except Exception:
            return JSONResponse (status_code =500 ,content ={"error":"SystemFault","message":"Internal authentication error."})

        if is_blacklisted :
            return JSONResponse (
            status_code =401 ,content ={"error":"Unauthorized","message":"Token has been revoked. Please log in again."}
            )

        request .state .user_id =str (user_id )
        return await call_next (request )
