import asyncio
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

from backend.core.config import settings
from backend.database.base import Base

sys.path.insert(0, '.')


config = context.config
if config.get_main_option("sqlalchemy.url") is None:
    config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option('sqlalchemy.url')
    context.configure(url=url, target_metadata=target_metadata,
                      literal_binds=True, compare_type=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection,
                      target_metadata=target_metadata, compare_type=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    cmd_line_args = context.get_x_argument(as_dictionary=True)
    url = cmd_line_args.get(
        "sqlalchemy.url") or config.get_main_option("sqlalchemy.url")
    if url is None:
        url = settings.database_url

    parsed_url = make_url(url)
    if "+async" not in parsed_url.drivername:
        connectable = create_engine(url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            do_run_migrations(connection)
        connectable.dispose()
        return

    engine_config = dict(config.get_section(config.config_ini_section, {}))
    engine_config["sqlalchemy.url"] = str(url)

    connectable = async_engine_from_config(
        engine_config,
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
