import os
import socket
import subprocess
import time
import uuid
from collections.abc import Generator
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def run_command(command: str) -> None:
    """Executes a shell command and streams its output in real-time.

    Args:
        command: The shell command to execute.
    """ 
    print(f"\n--- Running command: {command} ---")
    process = subprocess.Popen(
        command,
        shell=True,  # nosec B602
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    if process.stdout:
        for line in process.stdout:
            print(line, end="")
    process.wait()
    if process.returncode != 0:
        pytest.fail(f"Command failed with exit code {process.returncode}: {command}")
    print(f"--- Command finished: {command} ---")


@pytest.fixture(scope="session", autouse=True)
def db_session() -> Generator:
    """Manages the test database lifecycle.

    This fixture is session-scoped and runs automatically for all tests.
    It creates a unique schema for the test run, applies migrations,
    and cleans up by dropping the schema afterwards.

    Yields:
        The SQLAlchemy engine instance.
    """
    print("\n--- Setting up database session ---")

    fixture_dir = Path("tests/fixtures/3304557/2025-08-23/")
    fixture_path = fixture_dir / "Anexos.zip"
    if not fixture_path.exists():
        fixture_dir.mkdir(parents=True, exist_ok=True)
        with ZipFile(fixture_path, "w") as zf:
            zf.writestr("dummy_document.pdf", b"dummy pdf content")

    host = "127.0.0.1"
    os.environ["POSTGRES_HOST"] = host
    os.environ["PUBSUB_EMULATOR_HOST"] = f"{host}:8085"
    os.environ["GCP_GCS_HOST"] = f"http://{host}:8086"

    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db_name = os.getenv("POSTGRES_DB", "public_detective")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    schema_name = f"test_schema_{uuid.uuid4().hex}"
    os.environ["POSTGRES_DB_SCHEMA"] = schema_name

    timeout = 30
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                break
        except (TimeoutError, ConnectionRefusedError):
            time.sleep(1)
    else:
        pytest.fail(f"Could not connect to postgres at {host}:{port} after {timeout} seconds")

    db_url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    # Create an engine that automatically sets the search_path for all connections
    connect_args = {"options": f"-csearch_path={schema_name}"}
    engine = create_engine(db_url, connect_args=connect_args)

    try:
        with engine.connect() as connection:
            print(f"Creating schema {schema_name}...")
            connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            connection.commit()

        print("Running Alembic migrations...")
        run_command("poetry run alembic upgrade head")

        yield engine

    finally:
        print("\n--- Tearing down database session ---")
        with engine.connect() as connection:
            print(f"Dropping schema {schema_name}...")
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
        engine.dispose()
        print("Database session torn down.")
