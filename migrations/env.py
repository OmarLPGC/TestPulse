import os
from logging.config import fileConfig

from alembic import context
from database import Base
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url
from testpulse.config import load_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url():
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if test_database_url:
        return make_url(test_database_url)
    return load_settings().database_url


def run_migrations_offline():
    url = get_database_url().render_as_string(hide_password=False).replace("%", "%%")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(get_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
