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

    bootstrap_business_name: str = "Nexora HVAC"
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    ai_provider: str = "local"
    ai_base_url: str = "http://localhost:11434/v1"
    ai_api_key: str = "local"
    ai_model: str = "local-model"

    default_timezone: str = "America/New_York"
    connector_encryption_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://127.0.0.1:8000/api/connectors/google/callback"

    hubspot_private_app_token: str = ""
    outbound_webhook_url: str = ""
    outbound_webhook_secret: str = ""
    intake_api_key: str = ""

    automation_enabled: bool = True
    automation_poll_seconds: int = 30
    gmail_poll_seconds: int = 60

    session_max_age_seconds: int = 28800
    allowed_hosts: str = "127.0.0.1,localhost,testserver"
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 900

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def live_mode(self) -> bool:
        return not self.demo_mode

    @property
    def allowed_host_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    def validate_runtime(self) -> None:
        if self.app_env == "production":
            if self.demo_mode:
                raise RuntimeError("DEMO_MODE must be false in production.")
            if self.app_secret == "change-this-before-production" or len(self.app_secret) < 32:
                raise RuntimeError("APP_SECRET must be a strong production secret.")
            if not self.connector_encryption_key:
                raise RuntimeError("CONNECTOR_ENCRYPTION_KEY is required in production.")
            if not self.bootstrap_admin_email or len(self.bootstrap_admin_password) < 12:
                raise RuntimeError(
                    "BOOTSTRAP_ADMIN_EMAIL and a 12+ character BOOTSTRAP_ADMIN_PASSWORD are required in production."
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
