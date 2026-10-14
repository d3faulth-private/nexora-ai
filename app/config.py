from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Nexora AI"
    app_env: str = "development"
    app_secret: str = "change-this-before-production"
    database_url: str = "sqlite:///./nexora.db"

    demo_mode: bool = True
    demo_email: str = "admin@nexora.local"
    demo_password: str = "nexora-demo"

    ai_provider: str = "local"
    ai_base_url: str = "http://localhost:11434/v1"
    ai_api_key: str = "local"
    ai_model: str = "local-model"

    default_timezone: str = "America/New_York"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
