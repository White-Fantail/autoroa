import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def cors_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def preflight(client: TestClient, origin: str, headers: str = "authorization"):
    return client.options(
        "/api/v1/admin/dashboard",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": headers,
        },
    )


def test_explicit_staging_origin_allows_authorization_preflight():
    origin = "https://carfolio-web-git-staging-nomadonghos-projects.vercel.app"
    client = cors_client(Settings(cors_origins=origin))

    response = preflight(client, origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "Authorization" in response.headers["access-control-allow-headers"]


def test_localhost_and_loopback_origins_are_supported():
    origins = "http://localhost:3000, http://127.0.0.1:3000"
    client = cors_client(Settings(cors_origins=origins))

    for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        assert preflight(client, origin).headers["access-control-allow-origin"] == origin


def test_configured_carfolio_vercel_preview_is_allowed():
    origin = "https://carfolio-web-git-feature-login-nomadonghos-projects.vercel.app"
    settings = Settings(
        app_env="staging",
        auth_mode="supabase",
        cors_origins="https://staging.carfolio.co.nz",
        cors_vercel_preview_project="carfolio-web",
        cors_vercel_preview_team="nomadonghos-projects",
    )

    response = preflight(cors_client(settings), origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize(
    "origin",
    [
        "https://unrelated-site.vercel.app",
        "https://carfolio-web-git-feature-other-team.vercel.app",
        "http://carfolio-web-git-feature-nomadonghos-projects.vercel.app",
    ],
)
def test_untrusted_vercel_origins_are_rejected(origin: str):
    settings = Settings(
        app_env="staging",
        auth_mode="supabase",
        cors_origins="https://staging.carfolio.co.nz",
        cors_vercel_preview_project="carfolio-web",
        cors_vercel_preview_team="nomadonghos-projects",
    )

    response = preflight(cors_client(settings), origin)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_production_stable_origin_does_not_enable_previews():
    settings = Settings(
        app_env="production",
        auth_mode="supabase",
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="test-key",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
        cors_origins="https://carfolio.co.nz",
    )
    client = cors_client(settings)

    allowed = preflight(client, "https://carfolio.co.nz")
    preview = preflight(
        client, "https://carfolio-web-git-main-nomadonghos-projects.vercel.app"
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://carfolio.co.nz"
    assert preview.status_code == 400
    assert "access-control-allow-origin" not in preview.headers


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        "https://carfolio.co.nz/",
        "https://carfolio.co.nz/path",
        "carfolio.co.nz",
    ],
)
def test_malformed_or_wildcard_origins_are_rejected(origins: str):
    with pytest.raises(ValidationError):
        Settings(cors_origins=origins)


def test_origin_parser_trims_ignores_empty_values_and_deduplicates():
    settings = Settings(
        cors_origins=" https://staging.carfolio.co.nz, ,https://staging.carfolio.co.nz "
    )

    assert settings.cors_origins == ["https://staging.carfolio.co.nz"]


def test_vercel_preview_scope_must_be_complete():
    with pytest.raises(ValidationError):
        Settings(cors_vercel_preview_project="carfolio-web")


def test_empty_vercel_preview_values_leave_previews_disabled():
    settings = Settings(
        cors_vercel_preview_project="",
        cors_vercel_preview_team="",
    )

    assert settings.cors_origin_regex is None


def test_production_rejects_vercel_preview_configuration():
    with pytest.raises(ValidationError, match="only be enabled in staging"):
        Settings(
            app_env="production",
            auth_mode="supabase",
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="test-key",
            supabase_jwt_issuer="https://example.supabase.co/auth/v1",
            cors_origins="https://carfolio.co.nz",
            cors_vercel_preview_project="carfolio-web",
            cors_vercel_preview_team="nomadonghos-projects",
        )


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_deployed_environments_require_explicit_origins(app_env: str):
    values = {"app_env": app_env, "auth_mode": "supabase"}
    if app_env == "production":
        values.update(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="test-key",
            supabase_jwt_issuer="https://example.supabase.co/auth/v1",
        )

    with pytest.raises(ValidationError, match="explicit CORS_ORIGINS"):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "origin",
    [
        "https://carfolio.co.nz:not-a-port",
        "https://car folio.co.nz",
        "https://carfolio_.co.nz",
        "https://[not-an-ipv6-address]",
    ],
)
def test_malformed_authorities_are_rejected(origin: str):
    with pytest.raises(ValidationError):
        Settings(cors_origins=origin)
