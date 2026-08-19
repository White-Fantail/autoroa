import uuid

from app.achievements import AchievementDefinition, UserAchievementAward, UserAchievementState
from app.models import Profile
from app.profile_achievements import UserAchievementSeen
from sqlalchemy import select


def _identity():
    auth_id = uuid.uuid4()
    return auth_id, {"Authorization": f"Bearer dev:{auth_id}"}


def test_secret_achievement_is_masked_until_earned(client, db):
    auth_id, headers = _identity()
    assert client.get("/api/v1/me/achievement-profile", headers=headers).status_code == 200
    profile = db.scalar(select(Profile).where(Profile.auth_user_id == str(auth_id)))
    secret = AchievementDefinition(
        key="test-secret",
        name="Hidden name",
        description="Hidden condition",
        category="SPECIAL",
        visibility="SECRET",
        criteria={"metric": "x", "op": "gte", "value": 1},
    )
    db.add(secret)
    db.commit()
    response = client.get("/api/v1/me/achievement-profile", headers=headers)
    card = next(item for item in response.json()["achievements"] if item["id"] == str(secret.id))
    assert card["key"] is None
    assert card["name"] == "Secret achievement"
    assert "condition" not in card["description"].lower()

    db.add(UserAchievementState(user_id=profile.id, achievement_id=secret.id, earned_count=1))
    db.commit()
    response = client.get("/api/v1/me/achievement-profile", headers=headers)
    card = next(item for item in response.json()["achievements"] if item["id"] == str(secret.id))
    assert card["name"] == "Hidden name"
    assert card["earned"] is True


def test_featured_achievements_must_be_active_and_earned(client, db):
    auth_id, headers = _identity()
    client.get("/api/v1/me/achievement-profile", headers=headers)
    profile = db.scalar(select(Profile).where(Profile.auth_user_id == str(auth_id)))
    earned = AchievementDefinition(key="earned-test", name="Earned", description="Earned", category="STARTER", criteria={"metric":"x","op":"gte","value":1})
    locked = AchievementDefinition(key="locked-test", name="Locked", description="Locked", category="STARTER", criteria={"metric":"y","op":"gte","value":1})
    db.add_all([earned, locked]); db.flush()
    db.add(UserAchievementState(user_id=profile.id, achievement_id=earned.id, earned_count=1))
    db.commit()

    response = client.put("/api/v1/me/featured-achievements", headers=headers, json={"achievement_ids":[str(locked.id)]})
    assert response.status_code == 422
    response = client.put("/api/v1/me/featured-achievements", headers=headers, json={"achievement_ids":[str(earned.id)]})
    assert response.status_code == 200
    assert response.json()["featured_achievement_ids"] == [str(earned.id)]


def test_achievement_feed_only_returns_unseen_awards(client, db):
    auth_id, headers = _identity()
    client.get("/api/v1/me/achievement-profile", headers=headers)
    profile = db.scalar(select(Profile).where(Profile.auth_user_id == str(auth_id)))
    badge = AchievementDefinition(key="feed-test", name="Feed test", description="New badge", category="STARTER", criteria={"metric":"x","op":"gte","value":1})
    db.add(badge); db.flush()
    award = UserAchievementAward(award_key=f"feed:{profile.id}", user_id=profile.id, achievement_id=badge.id, metadata_json={})
    db.add(award); db.commit()

    response = client.get("/api/v1/me/achievement-feed", headers=headers)
    assert response.status_code == 200
    assert [item["award_id"] for item in response.json()] == [str(award.id)]
    response = client.post("/api/v1/me/achievement-feed/seen", headers=headers, json={"award_ids":[str(award.id)]})
    assert response.status_code == 200 and response.json()["seen"] == 1
    assert db.get(UserAchievementSeen, (profile.id, award.id)) is not None
    assert client.get("/api/v1/me/achievement-feed", headers=headers).json() == []
