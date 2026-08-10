from functools import lru_cache
import ipaddress
from pathlib import Path
import re
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./carfolio.db"
    auth_mode: str = "development"
    dev_auth_secret: str = "local-only-secret"
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    openai_api_key: str | None = None
    google_maps_api_key: str | None = None
    ocr_provider: str = "mock"
    maps_provider: str = "mock"
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ]
    cors_vercel_preview_project: str | None = None
    cors_vercel_preview_team: str | None = None
    max_upload_bytes: int = 10_000_000
    local_media_dir: str = str(Path(__file__).resolve().parents[1] / ".local-media")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value):
        values = value.split(",") if isinstance(value, str) else value
        return [origin.strip() for origin in values if origin.strip()]

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if any(character.isspace() for character in origin):
                raise ValueError("CORS_ORIGINS entries cannot contain whitespace")
            try:
                parsed = urlsplit(origin)
                hostname = parsed.hostname
                parsed.port
            except ValueError as error:
                raise ValueError("CORS_ORIGINS entries must contain valid authorities") from error
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or not hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ORIGINS entries must be complete HTTP(S) origins without paths, "
                    "trailing slashes, credentials, queries, fragments, or wildcards"
                )
            try:
                ipaddress.ip_address(hostname)
            except ValueError:
                labels = hostname.split(".")
                if len(hostname) > 253 or any(
                    not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                    for label in labels
                ):
                    raise ValueError("CORS_ORIGINS entries must contain valid hostnames")
        return list(dict.fromkeys(origins))

    @field_validator("cors_vercel_preview_project", "cors_vercel_preview_team", mode="before")
    @classmethod
    def validate_vercel_scope(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not value:
            return None
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value):
            raise ValueError("Vercel project and team values must be valid DNS labels")
        return value

    @model_validator(mode="after")
    def production_secrets(self):
        if self.app_env not in {"development", "test"} and "cors_origins" not in self.model_fields_set:
            raise ValueError("Deployed environments require an explicit CORS_ORIGINS allowlist")
        if bool(self.cors_vercel_preview_project) != bool(self.cors_vercel_preview_team):
            raise ValueError(
                "CORS_VERCEL_PREVIEW_PROJECT and CORS_VERCEL_PREVIEW_TEAM must be set together"
            )
        if self.cors_vercel_preview_project and self.app_env != "staging":
            raise ValueError("Vercel preview origins may only be enabled in staging")
        if self.auth_mode == "development" and self.app_env not in {"development","test"}:
            raise ValueError("Development authentication is restricted to local/test environments")
        if self.app_env == "production" and (not self.supabase_url or not self.supabase_service_role_key or not self.supabase_jwt_issuer or self.auth_mode != "supabase"):
            raise ValueError("Production requires Supabase authentication and server credentials")
        return self

    @property
    def cors_origin_regex(self) -> str | None:
        if not self.cors_vercel_preview_project:
            return None
        project = re.escape(self.cors_vercel_preview_project)
        team = re.escape(self.cors_vercel_preview_team or "")
        deployment_suffix = r"[a-z0-9]+(?:-[a-z0-9]+)*"
        return rf"^https://{project}-{deployment_suffix}-{team}\.vercel\.app$"

@lru_cache
def get_settings() -> Settings:
    return Settings()
