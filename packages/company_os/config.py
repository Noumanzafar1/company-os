from typing import Literal
from urllib.parse import urlparse

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    company_env: Literal["development", "test", "staging", "production"] = "development"
    auth_mode: Literal["development", "supabase"] = "development"
    database_url: SecretStr
    console_origin: str = "http://localhost:3000"
    console_secret: SecretStr
    dev_auth_secret: SecretStr = SecretStr("")
    supabase_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    live_sending_enabled: bool = False
    live_budget_usd: int = 0

    @model_validator(mode="after")
    def contain_environment(self) -> "Settings":
        if self.live_sending_enabled or self.live_budget_usd != 0:
            raise ValueError("Phase 2 permits no external effects or live budget")
        if len(self.console_secret.get_secret_value()) < 32:
            raise ValueError("CONSOLE_SECRET must be randomly generated")
        if self.auth_mode == "development":
            if self.company_env not in {"development", "test"}:
                raise ValueError("Development authentication is local/test only")
            if urlparse(self.console_origin).hostname not in {"localhost", "127.0.0.1"}:
                raise ValueError("Development authentication requires loopback origin")
            if len(self.dev_auth_secret.get_secret_value()) < 32:
                raise ValueError("DEV_AUTH_SECRET must be randomly generated")
        elif not self.supabase_url.startswith("https://"):
            raise ValueError("Managed authentication requires HTTPS")
        if self.company_env in {"staging", "production"}:
            if not self.console_origin.startswith("https://"):
                raise ValueError("Secure browser transport required")
            if "sslmode=verify-full" not in self.database_url.get_secret_value():
                raise ValueError("Verified TLS database transport required")
        return self
