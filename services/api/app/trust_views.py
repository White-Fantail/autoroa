import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .auth import Principal, admin_principal, current_principal
from .db import get_db
from .models import Profile
from .trust import UserTrustState, refresh_user_trust, trust_payload


trust_router = APIRouter(prefix="/api/v1")


@trust_router.get("/me/trust")
def my_trust(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    state = refresh_user_trust(db, principal.profile.id)
    db.commit()
    return trust_payload(state)


@trust_router.get("/admin/users/{user_id}/trust")
def admin_user_trust(
    user_id: uuid.UUID,
    _principal: Principal = Depends(admin_principal),
    db: Session = Depends(get_db),
):
    if db.get(Profile, user_id) is None:
        raise HTTPException(404, "User not found")
    state = refresh_user_trust(db, user_id)
    db.commit()
    return trust_payload(state)
