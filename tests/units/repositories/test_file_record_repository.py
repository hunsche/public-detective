from unittest.mock import MagicMock

import pytest
from models.file_record import NewFileRecord
from repositories.file_record import FileRecordRepository


@pytest.fixture
def mock_engine():
    """Fixture for a mocked database engine."""
    return MagicMock()


@pytest.fixture
def file_record_repository(mock_engine):
    """
    Fixture to create a FileRecordRepository with a mocked database engine.
    """
    return FileRecordRepository(engine=mock_engine)


def test_save_file_record(file_record_repository):
    # Arrange
    mock_conn = MagicMock()
    file_record_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    record = NewFileRecord(
        analysis_id=1,
        file_name="test.pdf",
        gcs_path="test/gcs/path",
        extension=".pdf",
        size_bytes=1234,
        nesting_level=0,
        included_in_analysis=True,
        exclusion_reason=None,
        prioritization_logic="high",
    )

    # Act
    file_record_repository.save_file_record(record)

    # Assert
    mock_conn.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
