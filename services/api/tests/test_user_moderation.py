import uuid

from app.models import Profile
from app.user_moderation import (
    ACTIVE,
    BANNED,
    SUSPENDED,
    UserModerationEvent,
    UserModerationState,
    contribution_allowed,
)


def auth_headers(user_id: uuid.UUID, *, admin: bool = False):
    suffix = ":admin" if admin else ""
    return {"Authorization": f"Bearer dev:{user_id}{suffix}"}


def create_profile(client, user_auth_id: uuid.UUID):
    response = client.get("/api/v1/vehicles", headers=auth_headers(user_auth_id))
    assert response.status_code == 200


def admin_profiles(client, admin_auth_id: uuid.UUID):
    response = client.get(
        "/api/v1/admin/users", headers=auth_headers(admin_auth_id, admin=True)
    )
    assert response.status_code == 200
    return response.json()


def profile_id_for(rows, auth_id: uuid.UUID) -> str:
    return next(item["id"] for item in rows if item["auth_user_id"] == str(auth_id))


def test_admin_can_suspend_ban_and_reactivate_user(client, db):
    admin_auth_id = uuid.uuid4()
    user_auth_id = uuid.uuid4()
    create_profile(client, user_auth_id)
    rows = admin_profiles(client, admin_auth_id)
    user_id = profile_id_for(rows, user_auth_id)

    suspended = client.patch(
        f"/api/v1/admin/users/{user_id}/moderation",
        headers=auth_headers(admin_auth_id, admin=True),
        json={"status": SUSPENDED, "reason": "Repeated inaccurate price submissions"},
    )
    assert suspended.status_code == 200
    assert suspended.json()["moderation_status"] == SUSPENDED
    assert suspended.json()["moderation_reason"] == "Repeated inaccurate price submissions"
    assert len(suspended.json()["moderation_history"]) == 1

    listed = admin_profiles(client, admin_auth_id)
    user = next(item for item in listed if item["id"] == user_id)
    assert user["moderation_status"] == SUSPENDED
    assert "moderation_history" not in user

    banned = client.patch(
        f"/api/v1/admin/users/{user_id}/moderation",
        headers=auth_headers(admin_auth_id, admin=True),
        json={"status": BANNED, "reason": "Continued abuse after suspension"},
    )
    assert banned.status_code == 200
    assert banned.json()["moderation_status"] == BANNED
    assert [item["new_status"] for item in banned.json()["moderation_history"][:2]] == [
        BANNED,
        SUSPENDED,
    ]

    active = client.patch(
        f"/api/v1/admin/users/{user_id}/moderation",
        headers=auth_headers(admin_auth_id, admin=True),
        json={"status": ACTIVE, "reason": "Restriction lifted after review"},
    )
    assert active.status_code == 200
    assert active.json()["moderation_status"] == ACTIVE
    assert contribution_allowed(db, uuid.UUID(user_id))


def test_restriction_requires_reason_and_admin_cannot_restrict_self(client):
    admin_auth_id = uuid.uuid4()
    user_auth_id = uuid.uuid4()
    create_profile(client, user_auth_id)
    rows = admin_profiles(client, admin_auth_id)
    user_id = profile_id_for(rows, user_auth_id)
    admin_id = profile_id_for(rows, admin_auth_id)

    missing_reason = client.patch(
        f"/api/v1/admin/users/{user_id}/moderation",
        headers=auth_headers(admin_auth_id, admin=True),
        json={"status": SUSPENDED},
    )
    assert missing_reason.status_code == 422

    self_ban = client.patch(
        f"/api/v1/admin/users/{admin_id}/moderation",
        headers=auth_headers(admin_auth_id, admin=True),
        json={"status": BANNED, "reason": "test"},
    )
    assert self_ban.status_code == 409


def test_suspended_user_cannot_submit_authenticated_price_board(client):
    admin_auth_id = uuid.uuid4()
    user_auth_id = uuid.uuid4()
    create_profile(client, user_auth_id)
    rows = admin_profiles(client, admin_auth_id)
    user_id = profile_id_for(rows, user_auth_id)

    suspended = client.patch(
        f"/api/v1/admin/users/{user_id}/moderation",
        headers=auth_headers(admin_auth_id, admin=True),
        json={"status": SUSPENDED, "reason": "Price contribution abuse"},
    )
    assert suspended.status_code == 200

    response = client.post(
        f"/api/v1/fuel-stations/{uuid.uuid4()}/user-price-board-submissions",
        headers=auth_headers(user_auth_id),
        files={"photo": ("board.jpg", b"not-an-image", "image/jpeg")},
    )
    assert response.status_code == 403


def test_moderation_state_helper_defaults_to_active(db):
    user_auth_id = uuid.uuid4()
    profile = Profile(auth_user_id=str(user_auth_id), display_name="Contributor")
    db.add(profile)
    db.commit()

    assert contribution_allowed(db, profile.id)

    db.add(
        UserModerationState(
            user_id=profile.id,
            status=BANNED,
            reason="Abuse",
        )
    )
    db.add(
        UserModerationEvent(
            user_id=profile.id,
            previous_status=ACTIVE,
            new_status=BANNED,
            reason="Abuse",
        )
    )
    db.commit()

    assert not contribution_allowed(db, profile.id)
