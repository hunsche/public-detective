"""This module contains the unit tests for the FileRecordsRepository."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from public_detective.models.file_records import NewFileRecord
from public_detective.repositories.file_records import FileRecordsRepository


def test_save_file_record() -> None:
    """Test the save_file_record method."""
    engine = MagicMock()
    mock_connection = engine.connect().__enter__()
    mock_result = mock_connection.execute.return_value
    expected_uuid = uuid4()
    mock_result.scalar_one.return_value = expected_uuid

    repo = FileRecordsRepository(engine)
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

    result_uuid = repo.save_file_record(record)

    mock_connection.execute.assert_called_once()
    mock_connection.commit.assert_called_once()
    assert result_uuid == expected_uuid


def test_get_all_file_records_by_analysis_id() -> None:
    """Test the get_all_file_records_by_analysis_id method."""
    engine = MagicMock()
    repo = FileRecordsRepository(engine)
    analysis_id = uuid4()

    with patch.object(repo.engine, "connect") as mock_connect:
        mock_connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all.return_value = [
            {"id": uuid4()}
        ]
        result = repo.get_all_file_records_by_analysis_id(str(analysis_id))
        assert len(result) == 1
        mock_connect.assert_called_once()
