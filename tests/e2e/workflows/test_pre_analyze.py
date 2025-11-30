import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.workflows.conftest import GcsCleanupManager, run_command


@pytest.mark.timeout(240)
def test_pre_analyze_command(db_session: Engine, gcs_cleanup_manager: GcsCleanupManager) -> None:
    """Tests the pre-analyze command in isolation.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
    """
    target_date_str = "2025-08-23"
    ibge_code = "3550308"
    max_items_to_process = 1

    gcs_prefix = gcs_cleanup_manager.prefix
    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"

    pre_analyze_command = (
        f"poetry run pd analysis --gcs-path-prefix {gcs_prefix} prepare "
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
