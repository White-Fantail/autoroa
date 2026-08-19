import json
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import jwt
from jwt import PyJWKClient
from fastapi import Depends, Header, HTTPException
from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import get_settings
from .db import Base, get_db
from .models import Profile


class AuthIdentity(Base):
    __tablename__ = "profile_auth_identities"

    auth_user_id: Mapped[str] = mapped_column(String, primary_key=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Principal:
    def __init__(self, profile: Profile, admin: bool = False, profile_ids: tuple[uuid.UUID, ...] | None = None):
        self.profile = profile
        self.admin = admin
        self.profile_ids = profile_ids or (profile.id,)


class LazyAdminPrincipal:
    """Admin principal that resolves the profile only when an endpoint actually needs it."""

    def __init__(self, db: Session, auth_id: str, claims: dict):
        self.admin = True
        self._db = db
        self._auth_id = auth_id
        self._claims = claims
        self._resolved: tuple[Profile, tuple[uuid.UUID, ...]] | None = None

    def _resolve(self) -> tuple[Profile, tuple[uuid.UUID, ...]]:
        if self._resolved is None:
            self._resolved = _resolve_profile(self._db, self._auth_id, self._claims)
        return self._resolved

    @property
    def profile(self) -> Profile:
        return self._resolve()[0]

    @property
    def profile_ids(self) -> tuple[uuid.UUID, ...]:
        return self._resolve()[1]


def _display_name(claims: dict) -> str | None:
    metadata = claims.get("user_metadata") or {}
    for key in ("full_name", "name", "user_name", "preferred_username"):
        value = metadata.get(key) or claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:120]
    email = claims.get("email")
    if isinstance(email, str) and "@" in email:
        return email.split("@", 1)[0][:120]
    return None


def _identity_email(claims: dict) -> str | None:
    email = claims.get("email")
    if not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    return normalized if normalized and "@" in normalized else None


def _identity_provider(claims: dict) -> str | None:
    metadata = claims.get("app_metadata") or {}
    provider = metadata.get("provider")
    return provider.strip().lower()[:40] if isinstance(provider, str) and provider.strip() else None


@lru_cache(maxsize=4)
def _jwk_client(supabase_url: str) -> PyJWKClient:
    """Reuse the JWKS client and its key cache across authenticated requests."""
    return PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")


def _decode_principal(authorization: str | None) -> tuple[str, bool, dict]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization[7:]
    settings = get_settings()
    claims: dict = {}
    try:
        if settings.auth_mode == "development" and token.startswith("dev:"):
            parts = token.split(":")
            auth_id = str(uuid.UUID(parts[1]))
            admin = len(parts) > 2 and parts[2] == "admin"
        else:
            if not settings.supabase_url or not settings.supabase_jwt_issuer:
                raise ValueError("Supabase authentication is not configured")
            signing_key = _jwk_client(settings.supabase_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                issuer=settings.supabase_jwt_issuer,
                audience=settings.supabase_jwt_audience,
            )
            auth_id = claims["sub"]
            admin = claims.get("app_metadata", {}).get("role") == "admin"
    except Exception as exc:
        raise HTTPException(401, "Invalid access token") from exc
    return auth_id, admin, claims


def _supabase_user_email(auth_user_id: str) -> str | None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    request = Request(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{auth_user_id}",
        headers={
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=3) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None
    email = payload.get("email") if isinstance(payload, dict) else None
    if not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    return normalized if normalized and "@" in normalized else None


def _hydrate_legacy_identity_emails(db: Session) -> None:
    """One-time compatibility work for a new identity, never a normal request-path task."""
    rows = list(db.scalars(select(AuthIdentity).where(AuthIdentity.email.is_(None)).limit(100)))
    changed = False
    for row in rows:
        email = _supabase_user_email(row.auth_user_id)
        if email:
            row.email = email
            row.updated_at = datetime.now(timezone.utc)
            changed = True
    if changed:
        db.flush()


def _resolve_profile(db: Session, auth_id: str, claims: dict) -> tuple[Profile, tuple[uuid.UUID, ...]]:
    email = _identity_email(claims)
    provider = _identity_provider(claims)
    suggested_name = _display_name(claims)
    dirty = False

    identity = db.get(AuthIdentity, auth_id)
    if identity is not None:
        profile = db.get(Profile, identity.profile_id)
        if profile is None or profile.deleted_at is not None:
            raise HTTPException(401, "Account profile is unavailable")
        if email and identity.email != email:
            identity.email = email
            dirty = True
        if provider and identity.provider != provider:
            identity.provider = provider
            dirty = True
        if dirty:
            identity.updated_at = datetime.now(timezone.utc)
    else:
        legacy_profile = db.scalar(select(Profile).where(Profile.auth_user_id == auth_id, Profile.deleted_at.is_(None)))
        if email:
            _hydrate_legacy_identity_emails(db)
            linked = db.scalar(
                select(AuthIdentity)
                .where(AuthIdentity.email == email)
                .order_by(AuthIdentity.created_at, AuthIdentity.auth_user_id)
                .limit(1)
            )
        else:
            linked = None

        if linked is not None:
            profile = db.get(Profile, linked.profile_id)
            if profile is None or profile.deleted_at is not None:
                linked = None
        if linked is None:
            profile = legacy_profile
        if profile is None:
            profile = Profile(auth_user_id=auth_id, display_name=suggested_name)
            db.add(profile)
            db.flush()

        identity = AuthIdentity(auth_user_id=auth_id, profile_id=profile.id, provider=provider, email=email)
        db.add(identity)
        dirty = True

    if not profile.display_name and suggested_name:
        profile.display_name = suggested_name
        dirty = True

    if email:
        linked_ids = tuple(
            dict.fromkeys(
                db.scalars(
                    select(AuthIdentity.profile_id)
                    .join(Profile, Profile.id == AuthIdentity.profile_id)
                    .where(AuthIdentity.email == email, Profile.deleted_at.is_(None))
                    .order_by(AuthIdentity.created_at, AuthIdentity.auth_user_id)
                ).all()
            )
        )
    else:
        linked_ids = (profile.id,)
    if profile.id not in linked_ids:
        linked_ids = (profile.id, *linked_ids)

    if dirty:
        db.commit()
    return profile, linked_ids


def current_principal(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> Principal:
    auth_id, admin, claims = _decode_principal(authorization)
    profile, linked_profile_ids = _resolve_profile(db, auth_id, claims)
    return Principal(profile, admin, linked_profile_ids)


def admin_principal(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    auth_id, admin, claims = _decode_principal(authorization)
    if not admin:
        raise HTTPException(403, "Admin role required")
    return LazyAdminPrincipal(db, auth_id, claims)
