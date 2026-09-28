import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add apps/api to path so we can import our models and settings
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

from core.config import settings
from models.base import Base  # We will create base.py to hold Base
from models import user  # Import to register models (triggers models/__init__.py)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return settings.SQLALCHEMY_DATABASE_URI


def get_connect_args() -> dict:
    """
    Return connect_args for the Alembic engine, matching what database.py does.

    In production (Supabase pooler): injects the ssl_context from
    settings.db_ssl_context, which handles the Supabase PgBouncer TLS
    certificate chain in the same way as the application engine.

    In development (localhost): returns an empty dict — no SSL needed.

    No SSL logic is duplicated here; the implementation lives entirely in
    settings.db_ssl_context (core/config.py).
    """
    ssl_ctx = settings.db_ssl_context
    if ssl_ctx is not None:
        return {"ssl_context": ssl_ctx}
    return {}


def run_migrations_offline() -> None:
    """
    Run migrations without a live DB connection.
    The URL is rendered into the migration SQL directly.
    SSL context is not applicable in offline mode.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations against a live database connection.
    Passes the same SSL connect_args as the application engine so that
    Supabase pooler TLS is negotiated correctly.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=get_connect_args(),
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
