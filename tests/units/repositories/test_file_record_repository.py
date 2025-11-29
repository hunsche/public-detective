"""This module contains the unit tests for the FileRecordsRepository."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.models.file_records import ExclusionReason, NewFileRecord, PrioritizationLogic
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


def test_set_files_as_included_empty(repository: FileRecordsRepository) -> None:
    """Tests that set_files_as_included returns early for empty list."""
    repository.set_files_as_included([])
    # Should not connect to DB
    repository.engine.connect.assert_not_called()


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
        prioritization_logic=PrioritizationLogic.NO_PRIORITY,
        prioritization_keyword=None,
        applied_token_limit=None,
        prepared_content_gcs_uris=None,
    )

    result_uuid = repository.save_file_record(record)

    mock_connection.execute.assert_called_once()
    mock_connection.commit.assert_called_once()
    assert result_uuid == expected_uuid


def test_save_file_record_with_optionals(repository: FileRecordsRepository) -> None:
    """Test saving a file record with optional fields populated."""
    mock_connection = repository.engine.connect().__enter__()
    expected_uuid = uuid4()
    mock_connection.execute.return_value.scalar_one.return_value = expected_uuid

    file_record = NewFileRecord(
        source_document_id=uuid4(),
        file_name="test.pdf",
        gcs_path="gs://bucket/test.pdf",
        extension="pdf",
        size_bytes=1024,
        nesting_level=0,
        included_in_analysis=False,
        exclusion_reason=ExclusionReason.TOKEN_LIMIT_EXCEEDED,
        prioritization_logic=PrioritizationLogic.BY_METADATA,
        prioritization_keyword="edital",
        applied_token_limit=None,
        prepared_content_gcs_uris=None,
    )

    result_id = repository.save_file_record(file_record)

    assert result_id == expected_uuid
    # Verify that optional enums were converted to names
    call_args = mock_connection.execute.call_args
    params = call_args[1]["parameters"]
    assert params["exclusion_reason"] == "TOKEN_LIMIT_EXCEEDED"
    assert params["prioritization_logic"] == "BY_METADATA"


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


def test_set_files_as_included_happy_path(repository: FileRecordsRepository) -> None:
    """Tests that the UPDATE statement is called for a list of file IDs."""
    file_ids = [uuid4(), uuid4()]
    repository.set_files_as_included(file_ids)
    mock_connection = repository.engine.connect().__enter__()
    mock_connection.execute.assert_called_once()
    mock_connection.commit.assert_called_once()
