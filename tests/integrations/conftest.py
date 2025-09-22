import os
import time
import uuid
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from public_detective.providers.config import ConfigProvider
from sqlalchemy import create_engine, text


@pytest.fixture(scope="function")
def db_session() -> Generator:
    os.environ.pop("GCP_SERVICE_ACCOUNT_CREDENTIALS", None)
    os.environ.pop("GCP_GCS_BUCKET_PROCUREMENTS", None)
    os.environ["GCP_PROJECT"] = "public-detective"

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
def integration_dependencies(db_session):
    """Provides real dependencies for integration tests."""
    from public_detective.providers.ai import AiProvider
    from public_detective.providers.gcs import GcsProvider
    from public_detective.providers.pubsub import PubSubProvider
    from public_detective.repositories.analyses import AnalysisRepository
    from public_detective.repositories.budget_ledger import BudgetLedgerRepository
    from public_detective.repositories.file_records import FileRecordsRepository
    from public_detective.repositories.procurements import ProcurementsRepository
    from public_detective.repositories.status_history import StatusHistoryRepository
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
