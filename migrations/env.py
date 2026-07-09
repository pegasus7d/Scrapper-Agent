from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend import config as app_config
from backend.db.models import Base
from backend.db.vectors import register_vec_extension

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The app's own config module is the single source of truth for the DB URL
# (DESIGN.md) — never a second, driftable copy in alembic.ini. Two override
# paths, both Alembic's own documented mechanisms, checked in order:
# `config.attributes["configure_url"]` for programmatic use (migrate.py
# passes the exact URL make_engine() was given — critical for tests, which
# use their own sqlite:///:memory:/tmp-file URLs, not the app default), and
# `alembic -x db_url=...` for generating a migration by hand against a
# scratch DB without touching the real one.
db_url = (
    config.attributes.get("configure_url")
    or context.get_x_argument(as_dictionary=True).get("db_url")
    or app_config.DATABASE_URL
)
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    `config.attributes["connection"]` (migrate.py's programmatic path) takes
    priority: reusing the caller's own connection is required for
    sqlite:///:memory: URLs specifically — confirmed for real that a fresh
    engine_from_config() here would migrate a completely separate, throwaway
    in-memory database, leaving the caller's own make_engine()-returned
    engine connected to an empty, unmigrated one (separate Engine objects
    never share an in-memory SQLite database). The CLI path (no caller to
    share a connection with) still builds its own Engine here.
    """
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # A migration may CREATE VIRTUAL TABLE ... USING vec0 (phase 6 step 7's
    # tables) — that module only exists once sqlite-vec is loaded on the
    # connection, same requirement as make_engine()'s own setup.
    register_vec_extension(connectable)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
