import pytest
from sqlalchemy import text
from source.models.procurement_analysis_status import ProcurementAnalysisStatus
from source.repositories.status_history import StatusHistoryRepository


def test_create_status_history_record(db_session):
    """
    Tests that a status history record is created correctly.
    """
    # Arrange
    # First, create a dummy analysis record to satisfy the foreign key constraint
    with db_session.connect() as connection:
        connection.execute(
            text(
                """
                INSERT INTO procurement_analyses (analysis_id, procurement_control_number, version_number, status)
                VALUES (999, 'test_control', 1, 'PENDING_ANALYSIS');
                """
            )
        )
        connection.commit()

    repo = StatusHistoryRepository(engine=db_session)
    analysis_id = 999
    status = ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS
    details = "Worker picked up task."

    # Act
    repo.create_record(analysis_id, status, details)

    # Assert
    with db_session.connect() as connection:
        result = connection.execute(
            text("SELECT analysis_id, status, details FROM procurement_analysis_status_history WHERE analysis_id = :id"),
            {"id": analysis_id},
        ).fetchone()

    assert result is not None
    assert result[0] == analysis_id
    assert result[1] == status.value
    assert result[2] == details
