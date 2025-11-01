"""This module contains integration tests for the AnalysisService."""

import pytest
from public_detective.services.analysis import AnalysisService
from public_detective.repositories.procurements import ProcessedFile
from unittest.mock import MagicMock


@pytest.fixture
def analysis_service():
    """Returns an AnalysisService instance for testing."""
    procurement_repo = MagicMock()
    analysis_repo = MagicMock()
    source_document_repo = MagicMock()
    file_record_repo = MagicMock()
    status_history_repo = MagicMock()
    budget_ledger_repo = MagicMock()
    ai_provider = MagicMock()
    gcs_provider = MagicMock()
    pubsub_provider = MagicMock()

    return AnalysisService(
        procurement_repo,
        analysis_repo,
        source_document_repo,
        file_record_repo,
        status_history_repo,
        budget_ledger_repo,
        ai_provider,
        gcs_provider,
        pubsub_provider,
    )


def test_prepare_ai_candidates_unsupported_extension_with_fallback(analysis_service):
    analysis_service.converter_service = MagicMock()
    analysis_service.converter_service.is_supported_for_conversion.return_value = True
    analysis_service.converter_service.convert_to_pdf.return_value = b"pdf content"
    """
    Tests that a file with an unsupported extension is converted to PDF
    when a fallback is available.
    """
    processed_file = ProcessedFile(
        source_document_id="1",
        relative_path="test.unsupported",
        content=b"%PDF-1.4",  # Simulate a PDF file with a wrong extension
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.inferred_extension == ".pdf"
    assert candidate.used_fallback_conversion is True
    assert candidate.ai_path.endswith(".pdf")
