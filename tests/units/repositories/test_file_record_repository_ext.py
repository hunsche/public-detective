from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.repositories.file_records import FileRecordsRepository


@pytest.fixture
def mock_engine() -> MagicMock:
    """Provides a mock SQLAlchemy engine."""
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


@pytest.fixture
def repository(mock_engine: MagicMock) -> FileRecordsRepository:
    """Provides a FileRecordsRepository instance with a mocked engine."""
    return FileRecordsRepository(engine=mock_engine)


def test_set_files_as_included_empty_list(repository: FileRecordsRepository) -> None:
    """Tests that no database call is made when an empty list is passed."""
    repository.set_files_as_included([])
    repository.engine.connect.return_value.__enter__.return_value.execute.assert_not_called()


def test_get_all_file_records_by_analysis_id(repository: FileRecordsRepository) -> None:
    """Tests fetching all file records for a given analysis ID."""
    analysis_id = uuid4()
    mock_record = {"id": uuid4(), "file_name": "test.pdf"}
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [mock_record]
    repository.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_result

    result = repository.get_all_file_records_by_analysis_id(str(analysis_id))

    assert len(result) == 1
    assert result[0]["file_name"] == "test.pdf"
    repository.engine.connect.return_value.__enter__.return_value.execute.assert_called_once()
