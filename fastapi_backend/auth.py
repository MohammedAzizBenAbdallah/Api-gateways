import httpx
from jose import jwt
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from config import KEYCLOAK_URL, KEYCLOAK_REALM

security = HTTPBearer()

# Simple in-memory cache for JWKS
jwks_cache = None

async def get_jwks():
    global jwks_cache
    if jwks_cache:
        return jwks_cache
        
    jwks_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(jwks_url, timeout=10.0)
            response.raise_for_status()
            jwks_cache = response.json()
            return jwks_cache
        except Exception as e:
            print(f"Failed to fetch JWKS from {jwks_url}: {str(e)}")
            raise

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    try:
        jwks = await get_jwks()
        
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
        
        if rsa_key:
            # Flexible issuer: support internal (container) or external (localhost) URL
            internal_iss = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
            external_iss = f"http://localhost:8080/realms/{KEYCLOAK_REALM}"
            
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience="account",
                options={
                    "verify_iss": True,
                    "verify_aud": True,
                    "verify_exp": True
                }
            )
            
            # Manual issuer check since it can vary
            if payload.get("iss") not in [internal_iss, external_iss]:
                 print(f"Issuer mismatch: {payload.get('iss')} not in [{internal_iss}, {external_iss}]")
                 raise jwt.JWTError("Invalid issuer")
                 
            return payload
            
    except Exception as e:
        print(f"JWT Verification Error: {str(e)}")
        # If JWKS fetch failed, it might be transient. For dev, clear cache to retry next time.
        global jwks_cache
        jwks_cache = None 
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    raise HTTPException(status_code=401, detail="Unauthorized")
