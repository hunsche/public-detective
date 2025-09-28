"""Unit tests for the SourceDocumentsRepository."""

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
