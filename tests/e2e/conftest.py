import asyncio
import os
import socket
import subprocess  # nosec B404
import tempfile
import threading
import time
import uuid
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from alembic import command
from alembic.config import Config as AlembicConfig
from filelock import FileLock
from google.api_core import exceptions
from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient
from public_detective.providers.config import ConfigProvider
from public_detective.providers.gcs import GcsProvider
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--pncp-control-number",
        action="store",
        default=None,
        help="Procurement control number to test.",
    )


def pytest_generate_tests(metafunc: Any) -> None:
    if "pncp_control_number" in metafunc.fixturenames and metafunc.function.__name__ == "test_debug_failed_conversion":
        number = metafunc.config.getoption("pncp_control_number")
        if number:
            metafunc.parametrize("pncp_control_number", [number])
        else:
            # Parametrize with an empty list to skip the test if no number is provided
            metafunc.parametrize("pncp_control_number", [])


@pytest.fixture(scope="function")
def gcs_provider() -> GcsProvider:
    """Provides a GCS provider for E2E tests."""
    return GcsProvider()


def get_free_port() -> int:
    """Finds a free port on the host.

    Returns:
        A free port number.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]  # type: ignore


class MockPNCP:
    """A mock PNCP server for E2E tests."""

    def __init__(self, port: int):
        self.port = port
        self.file_content = b""
        self.file_metadata: dict = {}
        self.server_app = web.Application()
        self.server_app.router.add_get("/orgaos/{cnpj}/compras/{year}/{sequence}/arquivos", self.get_file_metadata)
        self.server_app.router.add_get("/pncp-api/v1/contratacoes/{pncp_id}/arquivos/{file_id}", self.get_file_content)
        self.runner = web.AppRunner(self.server_app)
        self.site: web.TCPSite | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    async def get_file_metadata(self, request: web.Request) -> web.Response:  # noqa: F841
        """Serves the file metadata.

        Args:
            request: The incoming request.

        Returns:
            A web response with the file metadata.
        """
        return web.json_response(self.file_metadata)

    async def get_file_content(self, request: web.Request) -> web.Response:  # noqa: F841
        """Serves the file content.

        Args:
            request: The incoming request.

        Returns:
            A web response with the file content.
        """
        return web.Response(body=self.file_content)

    def run_server(self) -> None:
        """Runs the aiohttp server."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.runner.setup())
        self.site = web.TCPSite(self.runner, "localhost", self.port)
        self.loop.run_until_complete(self.site.start())
        self.loop.run_forever()

    def start(self) -> None:
        """Starts the server in a background thread."""
        self.server_thread = threading.Thread(target=self.run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        time.sleep(1)  # Give the server a moment to start

    def stop(self) -> None:
        """Stops the server."""
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

    @property
    def url(self) -> str:
        """Returns the base URL of the mock server."""
        return f"http://localhost:{self.port}"


@pytest.fixture(scope="function")
def mock_pncp_server() -> Generator[MockPNCP, None, None]:
    """Fixture to manage the mock PNCP server.

    Yields:
        The mock PNCP server.
    """
    port = get_free_port()
    server = MockPNCP(port)
    server.start()
    yield server
    server.stop()


def run_command(command_str: str, max_retries: int = 3, delay: int = 10) -> None:
    """Executes a shell command and streams its output in real-time.

    Args:
        command_str: The command to execute.
        max_retries: The maximum number of retries.
        delay: The delay between retries.
    """
    print(f"\n--- Running command: {command_str} ---")
    for _ in range(max_retries):
        process = subprocess.Popen(
            command_str,
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
        if process.returncode == 0:
            print(f"--- Command finished: {command_str} ---")
            return
        print(f"--- Command failed with exit code {process.returncode}. Retrying in {delay}s... ---")
        time.sleep(delay)
    pytest.fail(f"Command failed after {max_retries} attempts: {command_str}")


@pytest.fixture(scope="function")
def e2e_pubsub() -> Generator[tuple[PublisherClient, str], None, None]:
    """Sets up and tears down the Pub/Sub resources for an E2E test.

    Yields:
        A tuple with the publisher client and the topic path.
    """
    config = ConfigProvider.get_config()
    project_id = config.GCP_PROJECT
    run_id = uuid.uuid4().hex[:8]
    topic_name = f"test-topic-{run_id}"
    subscription_name = f"test-subscription-{run_id}"

    os.environ["GCP_PUBSUB_TOPIC_PROCUREMENTS"] = topic_name
    os.environ["GCP_PUBSUB_TOPIC_SUBSCRIPTION_PROCUREMENTS"] = subscription_name

    publisher = PublisherClient()
    subscriber = SubscriberClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_path = subscriber.subscription_path(project_id, subscription_name)

    try:
        publisher.create_topic(request={"name": topic_path})
        subscriber.create_subscription(request={"name": subscription_path, "topic": topic_path})
        yield publisher, topic_path
    finally:
        try:
            subscriber.delete_subscription(request={"subscription": subscription_path})
        except exceptions.NotFound:
            pass
        try:
            publisher.delete_topic(request={"topic": topic_path})
        except exceptions.NotFound:
            pass


def _setup_environment(run_id: str) -> str:
    config = ConfigProvider.get_config()
    schema_name = f"test_schema_{run_id}"
    os.environ["POSTGRES_DB_SCHEMA"] = schema_name
    os.environ["PUBSUB_EMULATOR_HOST"] = f"{config.POSTGRES_HOST}:8085"
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
    """Runs the Alembic migrations for the specified schema.

    Args:
        engine: The SQLAlchemy engine.
        schema_name: The name of the database schema.
    """
    alembic_cfg = AlembicConfig("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
    alembic_cfg.set_main_option("POSTGRES_DB_SCHEMA", schema_name)
    lock_path = Path(tempfile.gettempdir()) / "tests_alembic.lock"
    try:
        with FileLock(str(lock_path)):
            command.upgrade(alembic_cfg, "head")
    except Exception as e:
        pytest.fail(f"Alembic upgrade failed: {e}")


@pytest.fixture(scope="function")
def e2e_credentials() -> Generator[Path, None, None]:
    """
    Manages the lifecycle of temporary GCP credentials for an E2E test.

    It creates a temporary JSON file from the GCP_SERVICE_ACCOUNT_CREDENTIALS
    environment variable and sets GOOGLE_APPLICATION_CREDENTIALS to its path.
    The temporary file is deleted after the test runs.

    Yields:
        The path to the temporary credentials file.
    """
    run_id = uuid.uuid4().hex[:8]
    original_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    credentials_json = os.environ.get("GCP_SERVICE_ACCOUNT_CREDENTIALS")

    if not credentials_json:
        pytest.fail("GCP_SERVICE_ACCOUNT_CREDENTIALS must be set for E2E tests.")

    temp_credentials_path = Path(f"tests/.tmp/temp_credentials_{run_id}.json")
    temp_credentials_path.parent.mkdir(parents=True, exist_ok=True)
    temp_credentials_path.write_text(credentials_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(temp_credentials_path)

    yield temp_credentials_path

    # Teardown: A limpeza acontece aqui, depois que todos os testes que usam a fixture terminam.
    print("\n--- Tearing down E2E credentials ---")
    if temp_credentials_path.exists():
        temp_credentials_path.unlink()

    if original_credentials is None:
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    else:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = original_credentials
    print("--- E2E credentials torn down ---")


@pytest.fixture(scope="function")
def db_session(e2e_credentials: Path) -> Generator[Engine, None, None]:  # noqa: F841  # noqa: F841
    """
    Configures a fully isolated environment for a single E2E test function.

    Args:
        e2e_credentials: A fixture that manages temporary GCP credentials,
                         ensuring they are available for the duration of the test.
    """
    run_id = uuid.uuid4().hex[:8]
    schema_name = _setup_environment(run_id)
    engine = _create_engine(schema_name)
    _wait_for_db(engine)

    with engine.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema_name}"))
        connection.commit()

    _run_migrations(engine, schema_name)

    yield engine

    # A lógica de limpeza de credenciais foi removida daqui.
    print("\n--- Tearing down E2E database schema ---")
    with engine.connect() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        connection.commit()
    engine.dispose()
    print("--- E2E database schema torn down. ---")
    ConfigProvider._config = None


class GcsCleanupManager(BaseModel):
    """Manages the lifecycle of a temporary GCS folder for a test."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    prefix: str
    bucket_name: str
    gcs_provider: GcsProvider

    @model_validator(mode="after")
    def _create_test_marker_on_init(self) -> "GcsCleanupManager":
        """Creates a marker to identify the test folder after initialization."""
        self._create_test_marker()
        return self

    def _create_test_marker(self) -> None:
        """Creates a sentinel object with metadata to mark the folder as a test resource."""
        marker_blob_name = f"{self.prefix}/__test_marker__"
        self.gcs_provider.upload_file(
            bucket_name=self.bucket_name,
            destination_blob_name=marker_blob_name,
            content=b"",
            content_type="text/plain",
            metadata={
                "is_test": "true",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "run_id": self.prefix,
            },
        )

    def cleanup(self) -> None:
        """Deletes all objects under the prefix, including the marker."""
        # Use the provider's client, which is correctly configured for the emulator.
        gcs_client = self.gcs_provider.get_client()
        bucket = gcs_client.bucket(self.bucket_name)

        try:
            blobs_to_delete = list(bucket.list_blobs(prefix=self.prefix))
            print(f"--- Found {len(blobs_to_delete)} blobs to clean up for prefix {self.prefix} ---")
            for blob in blobs_to_delete:
                try:
                    blob.delete()
                except exceptions.NotFound:
                    pass  # Object might have been deleted by another process
            print(f"--- Cleanup successful for prefix {self.prefix} ---")
        except exceptions.NotFound:
            pass  # Bucket or prefix might already be gone


@pytest.fixture(scope="function")
def gcs_cleanup_manager(
    request: pytest.FixtureRequest,  # noqa: F841
    gcs_provider: GcsProvider,
    e2e_credentials: Path,  # noqa: F841
) -> Generator[GcsCleanupManager, None, None]:
    """A fixture to manage GCS cleanup for E2E tests.

    It creates a unique prefix for the test, marks it with a sentinel file,
    and cleans up everything under that prefix after the test runs.

    Args:
        request: The pytest request object.
        gcs_provider: A fixture that provides a configured GCS provider.
        e2e_credentials: The fixture that guarantees credentials are alive.

    Yields:
        An instance of the GcsCleanupManager.
    """
    config = ConfigProvider.get_config()
    bucket_name = config.GCP_GCS_BUCKET_PROCUREMENTS

    unique_id = uuid.uuid4().hex[:8]
    prefix = f"test-e2e-{unique_id}"

    manager = GcsCleanupManager(prefix=prefix, bucket_name=bucket_name, gcs_provider=gcs_provider)
    yield manager
    manager.cleanup()
