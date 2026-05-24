"""Alembic environment.

Imports the project's SQLAlchemy Base and *all* model modules so autogenerate
sees every table. Reads the connection URL from `core.config.settings`,
not from alembic.ini, so secrets never live in version control.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Project models — importing forces every table to be registered on Base.metadata.
from core.config import settings
from core.core.database_base import Base
from core.features.assets import models as _assets_models  # noqa: F401
from core.features.auth import models as _auth_models      # noqa: F401
from core.features.compliance import models as _compl_models  # noqa: F401
from core.features.transactions import models as _tx_models  # noqa: F401
from core.features.tribunal import models as _tribunal_models  # noqa: F401
from core.features.zkp import models as _zkp_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg_section = config.get_section(config.config_ini_section) or {}
    cfg_section["sqlalchemy.url"] = settings.database_url
    connectable = async_engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
