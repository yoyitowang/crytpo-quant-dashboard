"""Tests for config validation edge cases."""
import os
import pytest
from pydantic import SecretStr
from backend.app.core.config import Settings


def test_default_settings():
    s = Settings()
    assert s.PROJECT_NAME == "Crypto Funding Rate Dashboard"
    assert s.POSTGRES_USER == "postgres"
    assert s.POSTGRES_DB == "funding_rates"
    assert s.ENV == "dev"
    # REDIS_HOST may be overridden by env (e.g., docker sets it to "redis")
    assert s.REDIS_HOST in ("localhost", "redis")
    assert s.REDIS_PORT == "6379"


def test_database_url_format():
    s = Settings()
    url = s.DATABASE_URL
    assert url.startswith("postgresql+asyncpg://")
    assert "postgres" in url
    assert "funding_rates" in url


def test_aden_auth_not_available_by_default():
    s = Settings()
    assert s.aden_auth_available == False


def test_aden_auth_available_when_configured():
    s = Settings(
        ADEN_API_USER="test_user",
        ADEN_API_SIGNER="test_signer",
        ADEN_API_PRIVATE_KEY="test_key"
    )
    assert s.aden_auth_available == True


def test_env_override():
    s = Settings(ENV="prod")
    assert s.ENV == "prod"
    assert s.POSTGRES_PORT == "5432"


def test_custom_postgres_port():
    s = Settings(POSTGRES_PORT="6432")
    assert "6432" in s.DATABASE_URL
