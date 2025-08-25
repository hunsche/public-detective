from logging.config import fileConfig

from alembic import context
from providers.config import ConfigProvider
from sqlalchemy import engine_from_config, pool

sqlalchemy_config = context.config
project_config = ConfigProvider.get_config()

if sqlalchemy_config.config_file_name is not None:
    fileConfig(sqlalchemy_config.config_file_name)

url = (
    f"{project_config.POSTGRES_DRIVER}://"
    f"{project_config.POSTGRES_USER}:{project_config.POSTGRES_PASSWORD}@"
    f"{project_config.POSTGRES_HOST}:{project_config.POSTGRES_PORT}/"
    f"{project_config.POSTGRES_DB}"
)

sqlalchemy_config.set_main_option("sqlalchemy.url", url)

target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = sqlalchemy_config.get_main_option("sqlalchemy.url")
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

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get the schema from the environment variable, if it exists
    schema_name = project_config.POSTGRES_DB_SCHEMA

    # Create a new engine configuration that includes the schema in the search path
    config_section = sqlalchemy_config.get_section(sqlalchemy_config.config_ini_section, {})

    if schema_name:
        print(f"Alembic: Migrating within schema: {schema_name}")
        # This tells SQLAlchemy to issue a SET search_path command on new connections
        config_section["connect_args"] = {"options": f"-csearch_path={schema_name}"}

    connectable = engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=schema_name,  # Create alembic_version in the schema
            include_schemas=True,  # Important for multi-schema support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
