from functools import lru_cache
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8081"]
    max_upload_bytes: int = 10_000_000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value):
        return value.split(",") if isinstance(value, str) else value

    @model_validator(mode="after")
    def production_secrets(self):
        if self.auth_mode == "development" and self.app_env not in {"development","test"}:
            raise ValueError("Development authentication is restricted to local/test environments")
        if self.app_env == "production" and (not self.supabase_url or not self.supabase_service_role_key or not self.supabase_jwt_issuer or self.auth_mode != "supabase"):
            raise ValueError("Production requires Supabase authentication and server credentials")
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
