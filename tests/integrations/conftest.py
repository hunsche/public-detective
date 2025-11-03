import os
import tempfile
import time
import uuid
import zipfile
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from filelock import FileLock
from google.api_core import exceptions
from public_detective.providers.config import ConfigProvider
from public_detective.providers.gcs import GcsProvider
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


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
    db_session: Engine,  # noqa: F841
    request: pytest.FixtureRequest,  # noqa: F841
    gcs_provider: GcsProvider,
) -> Generator[GcsCleanupManager, None, None]:
    """A fixture to manage GCS cleanup for tests.

    It creates a unique prefix for the test, marks it with a sentinel file,
    and cleans up everything under that prefix after the test runs.

    Args:
        request: The pytest request object.
        gcs_provider: A fixture that provides a configured GCS provider.

    Yields:
        An instance of the GcsCleanupManager.
    """
    config = ConfigProvider.get_config()
    bucket_name = config.GCP_GCS_BUCKET_PROCUREMENTS

    unique_id = uuid.uuid4().hex[:8]
    prefix = f"test-integration/{unique_id}"

    manager = GcsCleanupManager(prefix=prefix, bucket_name=bucket_name, gcs_provider=gcs_provider)
    yield manager
    manager.cleanup()


@pytest.fixture(scope="function")
def gcs_provider() -> GcsProvider:
    """Provides a GCS provider for integration tests."""
    return GcsProvider()


@pytest.fixture(scope="function")
def db_session() -> Generator[Engine, Any, None]:
    """Creates a new database session for a test.

    Yields:
        The SQLAlchemy engine.
    """
    os.environ.pop("GCP_SERVICE_ACCOUNT_CREDENTIALS", None)

    fixture_dir = Path("tests/fixtures/3304557/2025-08-23/")
    fixture_path = fixture_dir / "Anexos.zip"
    if not fixture_path.exists():
        fixture_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(fixture_path, "w") as zf:
            zf.writestr("dummy_document.pdf", b"dummy pdf content")

    config = ConfigProvider.get_config()

    # Use localhost for services, as docker-compose exposes the ports to the host
    host = "localhost"
    os.environ["POSTGRES_HOST"] = host
    os.environ["PUBSUB_EMULATOR_HOST"] = f"{host}:8085"
    os.environ["GCP_GCS_HOST"] = f"http://{host}:8086"

    schema_name = f"test_schema_{uuid.uuid4().hex}"
    os.environ["POSTGRES_DB_SCHEMA"] = schema_name
    db_url = (
        f"postgresql://{config.POSTGRES_USER}:{config.POSTGRES_PASSWORD}@"
        f"{host}:{config.POSTGRES_PORT}/{config.POSTGRES_DB}"
    )
    engine = create_engine(db_url, connect_args={"options": f"-csearch_path={schema_name}"})

    # Wait for the database to be ready before proceeding
    for _ in range(60):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            break
        except Exception:
            time.sleep(2)
    else:
        pytest.fail("Database did not become available in time.")

    try:
        with engine.connect() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
            connection.execute(text(f"CREATE SCHEMA {schema_name}"))
            connection.commit()

            connection.execute(text(f"SET search_path TO {schema_name}"))
            connection.commit()

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        alembic_cfg.set_main_option("POSTGRES_DB_SCHEMA", schema_name)

        lock_path = Path(tempfile.gettempdir()) / "tests_alembic.lock"
        with FileLock(str(lock_path)):
            command.upgrade(alembic_cfg, "head")

        with engine.connect() as connection:
            connection.execute(text(f"SET search_path TO {schema_name}"))
            truncate_sql = text(
                f"TRUNCATE {schema_name}.procurements, {schema_name}.procurement_analyses, {schema_name}.file_records, "
                f"{schema_name}.procurement_analysis_status_history RESTART IDENTITY CASCADE;"
            )
            connection.execute(truncate_sql)
            connection.commit()
        yield engine
    finally:
        with engine.connect() as connection:
            connection.execute(text(f"SET search_path TO {schema_name}"))
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            connection.commit()
        engine.dispose()


@pytest.fixture
def integration_dependencies(db_session: Engine) -> dict[str, Any]:
    """Provides real dependencies for integration tests.

    Args:
        db_session: The SQLAlchemy engine.

    Returns:
        A dictionary of dependencies.
    """
    from public_detective.providers.ai import AiProvider
    from public_detective.providers.gcs import GcsProvider
    from public_detective.providers.pubsub import PubSubProvider
    from public_detective.repositories.analyses import AnalysisRepository
    from public_detective.repositories.budget_ledgers import BudgetLedgerRepository
    from public_detective.repositories.file_records import FileRecordsRepository
    from public_detective.repositories.procurements import ProcurementsRepository
    from public_detective.repositories.status_histories import StatusHistoryRepository
    from public_detective.services.analysis import Analysis

    pubsub_provider = PubSubProvider()
    procurement_repo = ProcurementsRepository(db_session, pubsub_provider)
    analysis_repo = AnalysisRepository(db_session)
    file_record_repo = FileRecordsRepository(db_session)
    status_history_repo = StatusHistoryRepository(db_session)
    budget_ledger_repo = BudgetLedgerRepository(db_session)
    ai_provider = AiProvider(output_schema=Analysis)
    gcs_provider = GcsProvider()

    return {
        "procurement_repo": procurement_repo,
        "analysis_repo": analysis_repo,
        "file_record_repo": file_record_repo,
        "status_history_repo": status_history_repo,
        "budget_ledger_repo": budget_ledger_repo,
        "ai_provider": ai_provider,
        "gcs_provider": gcs_provider,
        "pubsub_provider": pubsub_provider,
    }
