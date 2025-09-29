"""
Unit tests for the FileRecordsRepository to increase test coverage.
"""

from unittest.mock import MagicMock
from uuid import uuid4

from public_detective.repositories.file_records import FileRecordsRepository


def test_set_files_as_included_with_ids() -> None:
    """
    Tests that set_files_as_included correctly calls the database
    with a list of file IDs.
    """
    engine = MagicMock()
    mock_connection = engine.connect().__enter__()
    repo = FileRecordsRepository(engine)
    file_ids = [uuid4(), uuid4()]

    repo.set_files_as_included(file_ids)

    mock_connection.execute.assert_called_once()
    assert "UPDATE file_records" in str(mock_connection.execute.call_args.args[0])
    assert mock_connection.execute.call_args.args[1]["file_ids"] == file_ids
    mock_connection.commit.assert_called_once()


def test_set_files_as_included_empty_list() -> None:
    """
    Tests that set_files_as_included returns early and does not
    call the database when given an empty list.
    """
    engine = MagicMock()
    mock_connection = engine.connect().__enter__()
    repo = FileRecordsRepository(engine)

    repo.set_files_as_included([])

    mock_connection.execute.assert_not_called()
    mock_connection.commit.assert_not_called()
