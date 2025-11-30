import os
import subprocess  # nosec B404
import tempfile
import time
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from filelock import FileLock
from public_detective.providers.config import ConfigProvider
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _setup_environment(run_id: str) -> str:
    ConfigProvider.get_config()
    schema_name = f"test_web_int_{run_id}"
    os.environ["POSTGRES_DB_SCHEMA"] = schema_name
    return schema_name


def _create_engine(schema_name: str) -> Engine:
    config = ConfigProvider.get_config()
    db_url = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@"
        f"{config.POSTGRES_HOST}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    return create_engine(db_url, connect_args={"options": f"-csearch_path={schema_name}"})


def _wait_for_db(engine: Engine) -> None:
    for _ in range(30):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except Exception:
            time.sleep(1)
    pytest.fail("Database did not become available in time.")


def _run_migrations(engine: Engine, schema_name: str) -> None:
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
    alembic_cfg.set_main_option("POSTGRES_DB_SCHEMA", schema_name)
    lock_path = Path(tempfile.gettempdir()) / "tests_alembic.lock"
    try:
        with FileLock(str(lock_path)):
            command.upgrade(alembic_cfg, "head")
    except Exception as e:
        pytest.fail(f"Alembic upgrade failed: {e}")


def _seed_database(schema_name: str) -> None:
    """Populates the database with seed data using the pd CLI."""
    import shutil

    # Adjust path to find seed.sql from tests/integrations/web
    seed_file = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "seed.sql"
    if not seed_file.exists():
        pytest.fail(f"Seed file not found at {seed_file}")

    backup_file = seed_file.with_suffix(".sql.bak")

    # Backup the original seed file
    shutil.copy2(seed_file, backup_file)

    try:
        # Patch the seed file to fix unescaped quotes
        # We use sed to replace d'\u with d''\u
        cmd_sed = ["sed", "-i", "s/d'\\\\\\\\u/d''\\\\\\\\u/g", str(seed_file)]
        subprocess.run(cmd_sed, check=True)  # nosec B603

        # Run the pd command
        cmd_pd = ["poetry", "run", "pd", "db", "populate", "--schema", schema_name]
        subprocess.run(cmd_pd, check=True, capture_output=True, text=True)  # nosec B603
    except subprocess.CalledProcessError as e:
        stdout = e.stdout if hasattr(e, "stdout") else ""
        stderr = e.stderr if hasattr(e, "stderr") else ""
        pytest.fail(f"Database seeding failed:\nSTDOUT: {stdout}\nSTDERR: {stderr}")
    except Exception as e:
        pytest.fail(f"An unexpected error occurred during seeding: {e}")
    finally:
        # Restore the original seed file
        if backup_file.exists():
            shutil.move(backup_file, seed_file)


@pytest.fixture(scope="session")
def db_session() -> Generator[Engine, None, None]:
    """Sets up the database schema, migrates, and seeds it."""
    run_id = uuid.uuid4().hex[:8]
    schema_name = _setup_environment(run_id)
    engine = _create_engine(schema_name)
    _wait_for_db(engine)

    with engine.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema_name}"))
        connection.commit()

    _run_migrations(engine, schema_name)
    _seed_database(schema_name)

    yield engine

    with engine.connect() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        connection.commit()
    engine.dispose()
