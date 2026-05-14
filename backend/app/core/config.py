import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Crypto Funding Rate Dashboard"
    
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "funding_rates")
    
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: str = os.getenv("REDIS_PORT", "6379")

    # Aden / AsterDEX authenticated API (EIP-712 signing)
    # Get credentials from https://www.aden.io/en/api-wallet (Pro API)
    ADEN_API_USER: Optional[str] = os.getenv("ADEN_API_USER")
    ADEN_API_SIGNER: Optional[str] = os.getenv("ADEN_API_SIGNER")
    ADEN_API_PRIVATE_KEY: Optional[str] = os.getenv("ADEN_API_PRIVATE_KEY")
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def aden_auth_available(self) -> bool:
        return bool(self.ADEN_API_USER and self.ADEN_API_SIGNER and self.ADEN_API_PRIVATE_KEY)

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
