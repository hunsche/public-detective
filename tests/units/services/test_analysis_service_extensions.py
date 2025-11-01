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

    # Mock all converter services to prevent actual conversions in this unit test
    service.converter_service = MagicMock()
    service.image_converter_provider = MagicMock()

    # Simulate successful conversion for all types that require it
    service.converter_service.odt_to_pdf.return_value = b"pdf content"
    service.converter_service.xls_to_pdf.return_value = b"pdf content"
    service.converter_service.xlsx_to_pdf.return_value = b"pdf content"
    service.converter_service.xlsb_to_pdf.return_value = b"pdf content"
    service.image_converter_provider.tif_to_png.return_value = b"png content"
    service.image_converter_provider.bmp_to_png.return_value = b"png content"

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
    service.file_type_provider = MagicMock()
    service.file_type_provider.infer_extension.return_value = ".xyz"  # An unsupported type
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


def test_no_conversion_extension_is_processed_correctly() -> None:
    """Test that a supported file extension that requires no conversion is processed correctly."""
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
    service.converter_service = MagicMock()
    service.image_converter_provider = MagicMock()

    file_content = b"dummy pdf content"
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="test_file.pdf",
        content=file_content,
    )

    # Act
    candidates = service._prepare_ai_candidates([processed_file])

    # Assert
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.exclusion_reason is None
    assert candidate.ai_path == "test_file.pdf"
    assert candidate.ai_content == file_content
    # Ensure no conversion methods were called
    service.converter_service.odt_to_pdf.assert_not_called()
    service.image_converter_provider.tif_to_png.assert_not_called()
