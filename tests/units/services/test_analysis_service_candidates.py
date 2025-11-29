from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.models.file_records import ExclusionReason
from public_detective.providers.file_type import SPECIALIZED_IMAGE
from public_detective.repositories.procurements import ProcessedFile
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def analysis_service() -> AnalysisService:
    """Creates an AnalysisService instance with mocked dependencies."""
    procurement_repo = MagicMock()
    analysis_repo = MagicMock()
    source_document_repo = MagicMock()
    file_record_repo = MagicMock()
    status_history_repo = MagicMock()
    budget_ledger_repo = MagicMock()
    ai_provider = MagicMock()
    gcs_provider = MagicMock()
    http_provider = MagicMock()
    pubsub_provider = MagicMock()

    service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        http_provider=http_provider,
        pubsub_provider=pubsub_provider,
    )
    # Mock internal providers
    service.file_type_provider = MagicMock()
    service.image_converter_provider = MagicMock()
    service.converter_service = MagicMock()
    return service


def test_prepare_ai_candidates_lock_file(analysis_service: AnalysisService) -> None:
    """Tests that lock files are excluded."""
    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="~$lock.docx",
        content=b"content",
        extraction_failed=False,
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].exclusion_reason == ExclusionReason.LOCK_FILE


def test_prepare_ai_candidates_extraction_failed(analysis_service: AnalysisService) -> None:
    """Tests that files with extraction failures are excluded."""
    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="file.zip",
        content=b"",
        extraction_failed=True,
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].exclusion_reason == ExclusionReason.EXTRACTION_FAILED


def test_prepare_ai_candidates_specialized_image(analysis_service: AnalysisService) -> None:
    """Tests specialized image conversion."""
    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="image.ai",
        content=b"content",
        extraction_failed=False,
        raw_document_metadata={},
    )
    analysis_service.file_type_provider.get_file_type.return_value = SPECIALIZED_IMAGE
    analysis_service.image_converter_provider.to_png.return_value = b"png_content"

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].ai_content == b"png_content"
    assert candidates[0].ai_path == "image.png"
    assert candidates[0].exclusion_reason is None


def test_prepare_ai_candidates_specialized_image_failure(analysis_service: AnalysisService) -> None:
    """Tests specialized image conversion failure."""
    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="image.ai",
        content=b"content",
        extraction_failed=False,
        raw_document_metadata={},
    )
    analysis_service.file_type_provider.get_file_type.return_value = SPECIALIZED_IMAGE
    analysis_service.image_converter_provider.to_png.side_effect = Exception("Conversion failed")

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].exclusion_reason == ExclusionReason.CONVERSION_FAILED


def test_prepare_ai_candidates_fallback_conversion(analysis_service: AnalysisService) -> None:
    """Tests fallback conversion for unsupported extensions."""
    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="unknown.xyz",
        content=b"content",
        extraction_failed=False,
        raw_document_metadata={},
    )
    analysis_service.file_type_provider.get_file_type.return_value = "unknown"
    analysis_service.file_type_provider.infer_extension.return_value = ".pdf"
    analysis_service.converter_service.is_supported_for_conversion.return_value = True
    analysis_service.converter_service.convert_to_pdf.return_value = b"pdf_content"

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].ai_content == b"pdf_content"
    assert candidates[0].ai_path == "unknown.pdf"
    assert candidates[0].used_fallback_conversion is True


def test_prepare_ai_candidates_fallback_conversion_secondary(analysis_service: AnalysisService) -> None:
    """Tests secondary fallback conversion (to PNG) when primary fails."""
    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="unknown.xyz",
        content=b"content",
        extraction_failed=False,
        raw_document_metadata={},
    )
    analysis_service.file_type_provider.get_file_type.return_value = "unknown"
    analysis_service.file_type_provider.infer_extension.return_value = ".pdf"
    analysis_service.converter_service.is_supported_for_conversion.return_value = True
    analysis_service.converter_service.convert_to_pdf.side_effect = Exception("PDF failed")
    analysis_service.image_converter_provider.to_png.return_value = b"png_content"

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].ai_content == b"png_content"
    assert candidates[0].ai_path == "unknown.png"
    assert candidates[0].used_fallback_conversion is True


def test_prepare_ai_candidates_unsupported_extension(analysis_service: AnalysisService) -> None:
    """Tests unsupported extension with no fallback."""
    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="unknown.xyz",
        content=b"content",
        extraction_failed=False,
        raw_document_metadata={},
    )
    analysis_service.file_type_provider.get_file_type.return_value = "unknown"
    analysis_service.file_type_provider.infer_extension.return_value = None

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].exclusion_reason == ExclusionReason.UNSUPPORTED_EXTENSION


def test_resolve_redirects_success(analysis_service: AnalysisService) -> None:
    """Tests successful redirect resolution."""
    url = "http://google.com/url?q=http://target.com"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.url = "http://target.com"
    analysis_service.http_provider.head.return_value = mock_response

    resolved = analysis_service._resolve_redirects(url)
    assert resolved == "http://target.com"


def test_resolve_redirects_fallback_get(analysis_service: AnalysisService) -> None:
    """Tests fallback to GET when HEAD fails."""
    url = "http://google.com/url?q=http://target.com"
    mock_head_response = MagicMock()
    mock_head_response.status_code = 405  # Method Not Allowed
    analysis_service.http_provider.head.return_value = mock_head_response

    mock_get_response = MagicMock()
    mock_get_response.url = "http://target.com"
    analysis_service.http_provider.get.return_value = mock_get_response

    resolved = analysis_service._resolve_redirects(url)
    assert resolved == "http://target.com"


def test_resolve_redirects_exception(analysis_service: AnalysisService) -> None:
    """Tests exception handling during redirect resolution."""
    url = "http://google.com/url?q=http://target.com"
    analysis_service.http_provider.head.side_effect = Exception("Network error")

    resolved = analysis_service._resolve_redirects(url)
    assert resolved == url
