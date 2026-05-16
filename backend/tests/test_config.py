from pydantic import SecretStr
from backend.app.core.config import settings


def test_postgres_password_is_secret_str():
    assert isinstance(settings.POSTGRES_PASSWORD, SecretStr)


def test_database_url_contains_user():
    assert settings.POSTGRES_USER in settings.DATABASE_URL


def test_aden_private_key_is_optional_secret_str():
    if settings.ADEN_API_PRIVATE_KEY is not None:
        assert isinstance(settings.ADEN_API_PRIVATE_KEY, SecretStr)


def test_secret_str_not_in_repr():
    r = repr(settings.POSTGRES_PASSWORD)
    assert "postgres" not in r or "SecretStr" in r
