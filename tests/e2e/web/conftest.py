import os
import socket
import subprocess  # nosec B404
import tempfile
import threading
import time
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
import uvicorn
from alembic import command
from alembic.config import Config as AlembicConfig
from filelock import FileLock
from public_detective.providers.config import ConfigProvider
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def get_free_port() -> int:
    """Finds a free port on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]  # type: ignore


def _setup_environment(run_id: str) -> str:
    ConfigProvider.get_config()
    schema_name = f"test_web_e2e_{run_id}"
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


class UvicornThread(threading.Thread):
    def __init__(self, app_import_str: str, host: str, port: int):
        super().__init__()
        self.server = uvicorn.Server(config=uvicorn.Config(app_import_str, host=host, port=port, log_level="error"))
        self.daemon = True

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


@pytest.fixture(scope="session")
def live_server_url(db_session: Engine) -> Generator[str, None, None]:
    """Starts the web server and returns its URL."""
    # Ensure the env var is set (it should be from db_session, but let's be safe)
    # The db_session fixture sets os.environ["POSTGRES_DB_SCHEMA"] globally for the process.

    port = get_free_port()
    host = "127.0.0.1"

    # Start the server in a thread
    # We use the import string so uvicorn loads the app.
    # Since env vars are set, the app should pick up the schema.
    server_thread = UvicornThread("public_detective.web.main:app", host, port)
    server_thread.start()

    # Wait for the server to be ready
    url = f"http://{host}:{port}"
    health_url = f"{url}/health"

    import requests

    for _ in range(50):
        try:
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    else:
        server_thread.stop()
        pytest.fail("Server did not start in time.")

    yield url

    server_thread.stop()


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    return {
        **browser_context_args,
        "viewport": {
            "width": 1280,
            "height": 720,
        },
    }
