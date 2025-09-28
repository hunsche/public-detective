"""Unit tests for the AnalysisService supported extensions."""

from unittest.mock import MagicMock

import pytest
from public_detective.repositories.procurements import ProcessedFile
from public_detective.services.analysis import AnalysisService


@pytest.mark.parametrize("extension", AnalysisService._SUPPORTED_EXTENSIONS)
def test_supported_extensions_are_processed(extension: str) -> None:
    """Test that all supported file extensions are processed correctly."""
    # Arrange
    mock_dependencies = {
        "procurement_repo": MagicMock(),
        "analysis_repo": MagicMock(),
        "source_document_repo": MagicMock(),
        "file_record_repo": MagicMock(),
        "status_history_repo": MagicMock(),
        "budget_ledger_repo": MagicMock(),
        "ai_provider": MagicMock(),
        "gcs_provider": MagicMock(),
        "pubsub_provider": MagicMock(),
    }
    service = AnalysisService(**mock_dependencies)

    # Mock the converter service to avoid actual conversions
    service.converter_service = MagicMock()

    file_content = b"dummy content"
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path=f"test_file{extension}",
        content=file_content,
    )

    # Act
    candidates = service._prepare_ai_candidates([processed_file])

    # Assert
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.exclusion_reason is None, (
        f"Extension '{extension}' was unexpectedly excluded " f"with reason: {candidate.exclusion_reason}"
    )


def test_unsupported_extension_is_excluded() -> None:
    """Test that an unsupported file extension is correctly excluded."""
    # Arrange
    mock_dependencies = {
        "procurement_repo": MagicMock(),
        "analysis_repo": MagicMock(),
        "source_document_repo": MagicMock(),
        "file_record_repo": MagicMock(),
        "status_history_repo": MagicMock(),
        "budget_ledger_repo": MagicMock(),
        "ai_provider": MagicMock(),
        "gcs_provider": MagicMock(),
        "pubsub_provider": MagicMock(),
    }
    service = AnalysisService(**mock_dependencies)
    unsupported_extension = ".unsupported"
    processed_file = ProcessedFile(
        source_document_id="456",
        raw_document_metadata={},
        relative_path=f"test_file{unsupported_extension}",
        content=b"some content",
    )

    # Act
    candidates = service._prepare_ai_candidates([processed_file])

    # Assert
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.exclusion_reason is not None
    assert "Extensão de arquivo não suportada." in candidate.exclusion_reason
