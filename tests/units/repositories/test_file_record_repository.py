from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.models.file_records import NewFileRecord
from public_detective.repositories.file_records import FileRecordsRepository


@pytest.fixture
def mock_engine() -> MagicMock:
    """Fixture for a mocked database engine.

    Returns:
        A MagicMock object.
    """
    return MagicMock()


@pytest.fixture
def file_records_repository(mock_engine: MagicMock) -> FileRecordsRepository:
    """
    Fixture to create a FileRecordsRepository with a mocked database engine.

    Args:
        mock_engine: The mocked database engine.

    Returns:
        An instance of FileRecordsRepository.
    """
    return FileRecordsRepository(engine=mock_engine)


def test_save_file_record(file_records_repository: FileRecordsRepository) -> None:
    # Arrange
    mock_conn = MagicMock()
    file_records_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    record = NewFileRecord(
        analysis_id=uuid4(),
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
    file_records_repository.save_file_record(record)

    # Assert
    mock_conn.execute.assert_called_once()
    mock_conn.commit.assert_called_once()
