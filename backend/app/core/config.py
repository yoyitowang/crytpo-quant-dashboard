from __future__ import annotations
import os
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Crypto Funding Rate Dashboard"

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: SecretStr = SecretStr("postgres")
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "funding_rates"

    ENV: str = "dev"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: str = "6379"

    ADEN_API_USER: Optional[str] = None
    ADEN_API_SIGNER: Optional[str] = None
    ADEN_API_PRIVATE_KEY: Optional[SecretStr] = None

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def aden_auth_available(self) -> bool:
        return bool(self.ADEN_API_USER and self.ADEN_API_SIGNER and self.ADEN_API_PRIVATE_KEY)

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, env_file_encoding="utf-8")

settings = Settings()
