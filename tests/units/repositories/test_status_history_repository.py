from unittest.mock import MagicMock

import pytest
from models.procurement_analysis_status import ProcurementAnalysisStatus
from repositories.status_history import StatusHistoryRepository


@pytest.fixture
def mock_engine():
    """Fixture for a mocked database engine."""
    return MagicMock()


@pytest.fixture
def status_history_repository(mock_engine):
    """
    Fixture to create a StatusHistoryRepository with a mocked database engine.
    """
    return StatusHistoryRepository(engine=mock_engine)


def test_create_history_record_executes_insert(status_history_repository):
    """
    Should execute an INSERT statement with the correct parameters.
    """
    # Arrange
    mock_conn = MagicMock()
    status_history_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    analysis_id = 123
    status = ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS
    details = "Worker started processing."

    # Act
    status_history_repository.create_history_record(analysis_id, status, details)

    # Assert
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    sql_statement = str(args[0])
    params = args[1]

    assert "INSERT INTO procurement_analysis_status_history" in sql_statement
    assert params["analysis_id"] == analysis_id
    assert params["status"] == status.value
    assert params["details"] == details
    mock_conn.commit.assert_called_once()
