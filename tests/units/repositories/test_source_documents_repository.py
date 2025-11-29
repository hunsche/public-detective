"""Unit tests for the SourceDocumentsRepository."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.models.source_documents import NewSourceDocument
from public_detective.repositories.source_documents import SourceDocumentsRepository
from sqlalchemy import Engine


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


def test_save_source_document_with_url(source_documents_repo: SourceDocumentsRepository) -> None:
    """Test saving a source document with a URL."""
    mock_connection = source_documents_repo.engine.connect().__enter__()
    expected_uuid = uuid4()
    mock_connection.execute.return_value.scalar_one.return_value = expected_uuid

    source_document = NewSourceDocument(
        analysis_id=uuid4(),
        synthetic_id="doc1",
        title="Test Document",
        publication_date=datetime.now(UTC),
        document_type_name="Edital",
        url="http://example.com/doc.pdf",
        raw_metadata={"key": "value"},
    )

    result_id = source_documents_repo.save_source_document(source_document)

    assert result_id == expected_uuid
    call_args = mock_connection.execute.call_args
    params = call_args[1]["parameters"]
    assert params["url"] == "http://example.com/doc.pdf"


def test_save_source_document_without_url(source_documents_repo: SourceDocumentsRepository) -> None:
    """Test saving a source document without a URL."""
    mock_connection = source_documents_repo.engine.connect().__enter__()
    expected_uuid = uuid4()
    mock_connection.execute.return_value.scalar_one.return_value = expected_uuid

    source_document = NewSourceDocument(
        analysis_id=uuid4(),
        synthetic_id="doc2",
        title="Test Document No URL",
        publication_date=datetime.now(UTC),
        document_type_name="Edital",
        url=None,
        raw_metadata={"key": "value"},
    )

    result_id = source_documents_repo.save_source_document(source_document)

    assert result_id == expected_uuid
    call_args = mock_connection.execute.call_args
    params = call_args[1]["parameters"]
    assert params["url"] is None


@pytest.fixture
def source_documents_repo() -> SourceDocumentsRepository:
    mock_engine = MagicMock(spec=Engine)
    return SourceDocumentsRepository(mock_engine)


def test_get_source_documents_by_ids_empty(source_documents_repo: SourceDocumentsRepository) -> None:
    """Tests that get_source_documents_by_ids returns empty list for empty input."""
    assert source_documents_repo.get_source_documents_by_ids([]) == []
    source_documents_repo.engine.connect.assert_not_called()


def test_get_source_documents_by_ids_no_results(source_documents_repo: SourceDocumentsRepository) -> None:
    """Tests that get_source_documents_by_ids returns empty list when no docs found."""
    mock_conn = MagicMock()
    source_documents_repo.engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.mappings.return_value.fetchall.return_value = []

    assert source_documents_repo.get_source_documents_by_ids([uuid.uuid4()]) == []


def test_get_source_documents_by_analysis_id_no_results(source_documents_repo: SourceDocumentsRepository) -> None:
    """Tests that get_source_documents_by_analysis_id returns empty list when no docs found."""
    mock_conn = MagicMock()
    source_documents_repo.engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.mappings.return_value.fetchall.return_value = []

    assert source_documents_repo.get_source_documents_by_analysis_id(uuid.uuid4()) == []


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


def test_get_source_documents_by_analysis_id_returns_models(source_documents_repo: SourceDocumentsRepository) -> None:
    """Tests that get_source_documents_by_analysis_id returns models when docs found."""
    mock_conn = MagicMock()
    source_documents_repo.engine.connect.return_value.__enter__.return_value = mock_conn

    now = datetime.now(UTC)
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
    mock_conn.execute.return_value.mappings.return_value.fetchall.return_value = [mock_row]

    result = source_documents_repo.get_source_documents_by_analysis_id(mock_row["analysis_id"])

    assert len(result) == 1
    assert result[0].document_id == mock_row["id"]
    assert result[0].title == "Document"
    assert result[0].raw_metadata == {"foo": "bar"}
    mock_conn.execute.assert_called_once()
