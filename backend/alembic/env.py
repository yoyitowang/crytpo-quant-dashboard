import os
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

config = context.config

from backend.app.models.funding_rate import Base
from backend.app.models.spread_snapshot import SpreadSnapshot  # noqa: F401
target_metadata = Base.metadata

from backend.app.core.config import settings
password = settings.POSTGRES_PASSWORD
if hasattr(password, "get_secret_value"):
    password = password.get_secret_value()
db_url = f"postgresql://{settings.POSTGRES_USER}:{password}@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
