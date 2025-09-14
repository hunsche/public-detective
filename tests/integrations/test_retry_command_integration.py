import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from faker import Faker
from public_detective.cli.commands import retry
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from sqlalchemy import text
from sqlalchemy.engine import Engine

faker = Faker()


def setup_analysis(
    db_engine: Engine,
    status: ProcurementAnalysisStatus,
    retry_count: int = 0,
    updated_at: datetime | None = None,
) -> tuple[uuid.UUID, str]:
    if updated_at is None:
        updated_at = datetime.now(timezone.utc)

    analysis_id = uuid.uuid4()
    procurement_id = str(uuid.uuid4())
    version_number = 1
    object_description = faker.text()
    procurement_year = datetime.now(timezone.utc).year
    procurement_sequence = faker.random_int()
    publication_date = datetime.now(timezone.utc)
    last_update_date = datetime.now(timezone.utc)
    modality_id = faker.random_int()
    procurement_status_id = faker.random_int()

    with db_engine.connect() as conn:
        # Create the procurement record first
        conn.execute(
            text(
                """
                INSERT INTO procurements (
                    pncp_control_number, version_number, content_hash, raw_data,
                    object_description, is_srp, procurement_year, procurement_sequence,
                    pncp_publication_date, last_update_date, modality_id, procurement_status_id
                ) VALUES (
                    :procurement_id, :version_number, 'hash', '{}', :object_description,
                    :is_srp, :procurement_year, :procurement_sequence, :pncp_publication_date,
                    :last_update_date, :modality_id, :procurement_status_id
                )
                """
            ),
            {
                "procurement_id": procurement_id,
                "version_number": version_number,
                "object_description": object_description,
                "is_srp": False,
                "procurement_year": procurement_year,
                "procurement_sequence": procurement_sequence,
                "pncp_publication_date": publication_date,
                "last_update_date": last_update_date,
                "modality_id": modality_id,
                "procurement_status_id": procurement_status_id,
            },
        )

        # Now create the analysis record
        conn.execute(
            text(
                """
                INSERT INTO procurement_analyses (
                    analysis_id, procurement_control_number, version_number,
                    status, retry_count, updated_at, document_hash
                ) VALUES (
                    :analysis_id, :procurement_id, :version_number,
                    :status, :retry_count, :updated_at, 'hash'
                )
                """
            ),
            {
                "analysis_id": analysis_id,
                "procurement_id": procurement_id,
                "version_number": version_number,
                "status": status.value,
                "retry_count": retry_count,
                "updated_at": updated_at,
            },
        )
        conn.commit()
    return analysis_id, procurement_id


def test_retry_command_failed_analysis(db_session: Engine) -> None:
    """Test that a FAILED analysis is retried.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
    """
    db_engine = db_session
    old_time = datetime.now(timezone.utc) - timedelta(hours=7)
    analysis_id, procurement_id = setup_analysis(
        db_engine, status=ProcurementAnalysisStatus.ANALYSIS_FAILED, updated_at=old_time
    )

    mock_pubsub = MagicMock()
    runner = CliRunner()
    with (
        patch("public_detective.cli.commands.DatabaseManager.get_engine", return_value=db_engine),
        patch("public_detective.cli.commands.PubSubProvider", return_value=mock_pubsub),
    ):
        result = runner.invoke(retry)

    assert result.exit_code == 0, result.output
    assert "Successfully triggered 1 analyses for retry" in result.output
    mock_pubsub.publish.assert_called_once()

    # Check that a new analysis has been created
    with db_engine.connect() as conn:
        new_analysis_result = conn.execute(
            text(
                """
                SELECT retry_count, status FROM procurement_analyses
                WHERE procurement_control_number = :procurement_id
                AND analysis_id != :analysis_id
                """
            ),
            {"procurement_id": procurement_id, "analysis_id": analysis_id},
        ).fetchone()

    assert new_analysis_result is not None
    assert new_analysis_result[0] == 1  # retry_count
    assert new_analysis_result[1] == "ANALYSIS_IN_PROGRESS"


def test_retry_command_stale_in_progress(db_session: Engine) -> None:
    """Test that a stale IN_PROGRESS analysis is retried.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
    """
    db_engine = db_session
    stale_time = datetime.now(timezone.utc) - timedelta(hours=7)
    analysis_id, procurement_id = setup_analysis(
        db_engine,
        status=ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS,
        updated_at=stale_time,
    )

    mock_pubsub = MagicMock()
    runner = CliRunner()
    with (
        patch("public_detective.cli.commands.DatabaseManager.get_engine", return_value=db_engine),
        patch("public_detective.cli.commands.PubSubProvider", return_value=mock_pubsub),
    ):
        result = runner.invoke(retry)

    assert result.exit_code == 0, result.output
    assert "Successfully triggered 1 analyses for retry" in result.output
    mock_pubsub.publish.assert_called_once()

    # Check that a new analysis has been created
    with db_engine.connect() as conn:
        new_analysis_result = conn.execute(
            text(
                """
                SELECT retry_count, status FROM procurement_analyses
                WHERE procurement_control_number = :procurement_id
                AND analysis_id != :analysis_id
                """
            ),
            {"procurement_id": procurement_id, "analysis_id": analysis_id},
        ).fetchone()

    assert new_analysis_result is not None
    assert new_analysis_result[0] == 1  # retry_count
    assert new_analysis_result[1] == "ANALYSIS_IN_PROGRESS"


def test_retry_command_max_retries_exceeded(db_session: Engine) -> None:
    """Test that an analysis with max retries is not retried.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
    """
    db_engine = db_session
    setup_analysis(
        db_engine,
        status=ProcurementAnalysisStatus.ANALYSIS_FAILED,
        retry_count=3,  # Default max_retries is 3
    )

    mock_pubsub = MagicMock()
    runner = CliRunner()
    with (
        patch("public_detective.cli.commands.DatabaseManager.get_engine", return_value=db_engine),
        patch("public_detective.cli.commands.PubSubProvider", return_value=mock_pubsub),
    ):
        result = runner.invoke(retry)

    assert result.exit_code == 0
    assert "No analyses found to retry" in result.output
    mock_pubsub.publish.assert_not_called()


def test_retry_command_not_stale_in_progress(db_session: Engine) -> None:
    """Test that a recent IN_PROGRESS analysis is not retried.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
    """
    db_engine = db_session
    setup_analysis(
        db_engine,
        status=ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS,
        updated_at=datetime.now(timezone.utc),
    )

    mock_pubsub = MagicMock()
    runner = CliRunner()
    with (
        patch("public_detective.cli.commands.DatabaseManager.get_engine", return_value=db_engine),
        patch("public_detective.cli.commands.PubSubProvider", return_value=mock_pubsub),
    ):
        result = runner.invoke(retry)

    assert result.exit_code == 0
    assert "No analyses found to retry" in result.output
    mock_pubsub.publish.assert_not_called()
