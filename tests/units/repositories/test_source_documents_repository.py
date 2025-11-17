"""Unit tests for the SourceDocumentsRepository."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from public_detective.models.source_documents import NewSourceDocument
from public_detective.repositories.source_documents import SourceDocumentsRepository
from sqlalchemy.engine import Engine


def test_save_source_document() -> None:
    """Tests that the source document is saved correctly."""
    # Arrange
    mock_engine = MagicMock(spec=Engine)
    mock_connection = mock_engine.connect().__enter__()
    mock_result = mock_connection.execute.return_value
    expected_uuid = uuid4()
    mock_result.scalar_one.return_value = expected_uuid

    repo = SourceDocumentsRepository(engine=mock_engine)
    analysis_id = uuid4()
    new_document = NewSourceDocument(
        analysis_id=analysis_id,
        synthetic_id="a-fake-synthetic-id",
        title="Test Document",
        publication_date=None,
        document_type_name="Test Type",
        url="http://example.com",
        raw_metadata={"key": "value"},
    )

    # Act
    result_id = repo.save_source_document(new_document)

    # Assert
    mock_connection.execute.assert_called_once()
    mock_connection.commit.assert_called_once()
    assert result_id == expected_uuid


def test_get_source_documents_by_ids_returns_empty_when_list_is_empty() -> None:
    mock_engine = MagicMock(spec=Engine)
    repository = SourceDocumentsRepository(engine=mock_engine)

    result = repository.get_source_documents_by_ids([])

    assert result == []
    mock_engine.connect.assert_not_called()


def test_get_source_documents_by_ids_returns_empty_when_query_has_no_rows() -> None:
    mock_engine = MagicMock(spec=Engine)
    mock_connection = mock_engine.connect().__enter__()
    mock_connection.execute.return_value.mappings.return_value.fetchall.return_value = []

    repository = SourceDocumentsRepository(engine=mock_engine)
    ids = [uuid4()]

    result = repository.get_source_documents_by_ids(ids)

    assert result == []
    mock_connection.execute.assert_called_once()


def test_get_source_documents_by_ids_returns_models() -> None:
    mock_engine = MagicMock(spec=Engine)
    mock_connection = mock_engine.connect().__enter__()
    now = datetime.now(tz=UTC)
    mock_row = {
        "id": uuid4(),
        "analysis_id": uuid4(),
        "synthetic_id": "synthetic-id",
        "title": "Document",
        "publication_date": None,
        "document_type_name": "type",
        "url": "http://example.com",
        "raw_metadata": {"foo": "bar"},
        "created_at": now,
        "updated_at": now,
    }
    mock_connection.execute.return_value.mappings.return_value.fetchall.return_value = [mock_row]

    repository = SourceDocumentsRepository(engine=mock_engine)
    ids = [mock_row["id"]]

    result = repository.get_source_documents_by_ids(ids)

    assert len(result) == 1
    assert result[0].document_id == mock_row["id"]
    assert result[0].title == "Document"
    assert result[0].raw_metadata == {"foo": "bar"}
    mock_connection.execute.assert_called_once()
