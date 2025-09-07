import json
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import run_command


@pytest.fixture(scope="function")
def pre_analyze_e2e_setup():
    """Set up the environment for a single pre-analyze E2E test."""
    # Ensure E2E tests run against real GCP services, not an emulator.
    os.environ.pop("GCP_GCS_HOST", None)
    os.environ.pop("GCP_AI_HOST", None)
    # Pub/Sub can use an emulator if configured in the environment.

    # Set up credentials for the CLI command to run.
    gcs_credentials_path = os.path.expanduser("~/.gcp/credentials.json")
    if not os.path.exists(gcs_credentials_path):
        pytest.fail(f"Service account credentials not found at {gcs_credentials_path}")
    with open(gcs_credentials_path, "r") as f:
        gcs_credentials_json = f.read()

    os.environ["GCP_SERVICE_ACCOUNT_CREDENTIALS"] = gcs_credentials_json
    os.environ["GCP_PROJECT"] = "total-entity-463718-k1"

    yield

    # Teardown: Unset environment variables
    os.environ.pop("GCP_SERVICE_ACCOUNT_CREDENTIALS", None)
    os.environ.pop("TARGET_IBGE_CODES", None)


@pytest.mark.timeout(240)
def test_pre_analyze_command(db_session: Engine, pre_analyze_e2e_setup) -> None:
    """Tests the pre-analyze command in isolation.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
        pre_analyze_e2e_setup: The fixture to set up the E2E test environment.
    """
    target_date_str = "2025-08-23"
    ibge_code = "3550308"
    max_items_to_process = 1

    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"

    pre_analyze_command = (
        f"poetry run python -m source.cli pre-analyze "
        f"--start-date {target_date_str} --end-date {target_date_str} "
        f"--max-messages {max_items_to_process}"
    )
    run_command(pre_analyze_command)

    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        completed_analyses = (
            connection.execute(text("SELECT * FROM procurement_analyses WHERE status = 'PENDING_ANALYSIS'"))
            .mappings()
            .all()
        )
        assert len(completed_analyses) == max_items_to_process
