import logging 
from datetime import datetime ,timedelta ,timezone 

from jose import JWTError ,jwt 
import bcrypt

from backend .config import settings 

logger =logging .getLogger (__name__ )

def hash_password (password :str )->str :
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes[:72], salt)
    return hashed.decode('utf-8')

get_password_hash = hash_password

def verify_password (plain_password :str ,hashed_password :str )->bool :
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8')[:72],
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

def create_access_token (data :dict [str ,str |int ],expires_delta :timedelta |None =None )->str :
    
    allowed_keys ={"sub","role","org_id"}
    filtered_data :dict [str ,str |int ]={k :v for k ,v in data .items ()if k in allowed_keys }

    now =datetime .now (timezone .utc )
    if expires_delta :
        expire =now +expires_delta 
    else :
        expire =now +timedelta (minutes =settings .access_token_expire_minutes )

    filtered_data ["exp"]=int (expire .timestamp ())
    filtered_data ["iat"]=int (now .timestamp ())

    return jwt .encode (filtered_data ,settings .secret_key ,algorithm =settings .algorithm )

def decode_token (token :str )->dict [str ,str |int ]:
    
    try :
        return jwt .decode (token ,settings .secret_key ,algorithms =[settings .algorithm ])
    except JWTError as exc :
        raise ValueError ("Invalid or expired token.")from exc
