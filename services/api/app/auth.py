import uuid
import jwt
from jwt import PyJWKClient
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .models import Profile

class Principal:
    def __init__(self, profile: Profile, admin: bool=False): self.profile=profile; self.admin=admin
def current_principal(authorization: str|None=Header(None), db: Session=Depends(get_db)) -> Principal:
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Authentication required")
    token=authorization[7:]; settings=get_settings(); admin=False
    try:
        if settings.auth_mode == "development" and token.startswith("dev:"):
            parts=token.split(":"); auth_id=str(uuid.UUID(parts[1])); admin=len(parts)>2 and parts[2]=="admin"
        else:
            if not settings.supabase_url or not settings.supabase_jwt_issuer:
                raise ValueError("Supabase authentication is not configured")
            signing_key=PyJWKClient(f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json").get_signing_key_from_jwt(token)
            claims=jwt.decode(token, signing_key.key, algorithms=["RS256","ES256"], issuer=settings.supabase_jwt_issuer, audience=settings.supabase_jwt_audience)
            auth_id=claims["sub"]; admin=claims.get("app_metadata",{}).get("role")=="admin"
    except Exception as exc: raise HTTPException(401,"Invalid access token") from exc
    profile=db.scalar(select(Profile).where(Profile.auth_user_id==auth_id, Profile.deleted_at.is_(None)))
    if not profile:
        profile=Profile(auth_user_id=auth_id); db.add(profile); db.commit(); db.refresh(profile)
    return Principal(profile,admin)
def admin_principal(p: Principal=Depends(current_principal)):
    if not p.admin: raise HTTPException(403,"Admin role required")
    return p
