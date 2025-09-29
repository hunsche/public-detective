"""This module contains the unit tests for the FileRecordsRepository."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.models.file_records import NewFileRecord
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


def test_save_file_record(repository: FileRecordsRepository) -> None:
    """Test the save_file_record method."""
    mock_connection = repository.engine.connect().__enter__()
    mock_result = mock_connection.execute.return_value
    expected_uuid = uuid4()
    mock_result.scalar_one.return_value = expected_uuid

    record = NewFileRecord(
        source_document_id=uuid4(),
        file_name="test.pdf",
        gcs_path="test/path",
        extension="pdf",
        size_bytes=123,
        nesting_level=0,
        included_in_analysis=True,
        exclusion_reason=None,
        prioritization_logic="Test logic",
        prepared_content_gcs_uris=None,
    )

    result_uuid = repository.save_file_record(record)

    mock_connection.execute.assert_called_once()
    mock_connection.commit.assert_called_once()
    assert result_uuid == expected_uuid


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


def test_set_files_as_included_empty_list(repository: FileRecordsRepository) -> None:
    """Tests that no database call is made when an empty list is passed."""
    repository.set_files_as_included([])
    repository.engine.connect.return_value.__enter__.return_value.execute.assert_not_called()
