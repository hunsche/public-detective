from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from PIL import Image
from public_detective.repositories.procurements import ProcessedFile
from public_detective.services.analysis import AnalysisService

from tests.e2e.test_file_extensions import (
    create_docm,
    create_html,
    create_jfif,
    create_odg,
    create_pptx,
    create_txt,
    create_xlsm,
)


@pytest.fixture
def analysis_service(db_session: Any) -> AnalysisService:  # noqa: F841
    """Returns a fully initialized AnalysisService."""
    procurement_repo = Mock()
    analysis_repo = Mock()
    source_document_repo = Mock()
    file_record_repo = Mock()
    status_history_repo = Mock()
    budget_ledger_repo = Mock()
    ai_provider = Mock()
    gcs_provider = Mock()

    return AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
    )


def test_prepare_ai_candidates_specialized_image_conversion(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that a TIFF file is correctly converted to PNG via the specialized image pipeline."""
    tif_path = tmp_path / "sample.tif"
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(tif_path, "tiff")

    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.tif",
        content=tif_path.read_bytes(),
        extraction_failed=False,
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".png")
    assert candidate.ai_content is not None
    assert candidate.exclusion_reason is None


def test_prepare_ai_candidates_log_file(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that .log files are correctly treated as .txt files."""
    log_path = tmp_path / "sample.log"
    log_content = "this is a log"
    create_txt(log_path, content=log_content)
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.log",
        content=log_path.read_bytes(),
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".txt")
    assert candidate.ai_content == log_content.encode()
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


def test_prepare_ai_candidates_htm_file(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that .htm files are correctly treated as .txt files."""
    htm_path = tmp_path / "sample.htm"
    create_html(htm_path)
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.htm",
        content=htm_path.read_bytes(),
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".txt")
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


def test_prepare_ai_candidates_jfif_file(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that .jfif files are correctly treated as jpeg."""
    jfif_path = tmp_path / "sample.jfif"
    create_jfif(jfif_path)
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.jfif",
        content=jfif_path.read_bytes(),
    )
    analysis_service.file_type_provider.infer_extension = Mock(return_value=".jpeg")

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".jfif")
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


@pytest.mark.parametrize(
    "extension, generator",
    [
        ("pptx", create_pptx),
        ("xlsm", create_xlsm),
        ("docm", create_docm),
        ("odg", create_odg),
    ],
)
def test_prepare_ai_candidates_office_conversion(
    analysis_service: AnalysisService,
    tmp_path: Path,
    extension: str,
    generator: Callable[[Path], None],
) -> None:
    """Tests that new Office formats are correctly converted to PDF."""
    file_path = tmp_path / f"sample.{extension}"
    generator(file_path)
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path=f"sample.{extension}",
        content=file_path.read_bytes(),
    )

    # Mock the actual conversion to avoid dependency on LibreOffice in integration tests
    analysis_service.converter_service.convert_to_pdf = Mock(return_value=b"fake pdf content")

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".pdf")
    assert candidate.ai_content == b"fake pdf content"
    assert candidate.used_fallback_conversion is False  # It's now a direct conversion
    assert candidate.exclusion_reason is None


def test_tif_to_png_conversion(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that a .tif file is correctly converted to a .png file."""
    # Use a TIFF file, which the image converter can handle
    tif_path = tmp_path / "sample.tif"
    img = Image.new("RGB", (10, 10), color="cyan")
    img.save(tif_path, "tiff")

    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.tif",
        content=tif_path.read_bytes(),
    )

    # Mock the actual conversion to avoid dependency on ImageMagick
    analysis_service.image_converter_provider.tif_to_png = Mock(return_value=b"fake png content")

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".png")
    assert candidate.ai_content.startswith(b"\x89PNG")  # Check for PNG file signature
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


def test_prepare_ai_candidates_no_conversion_needed(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that a file not requiring conversion (e.g., PDF) is handled correctly."""
    pdf_path = tmp_path / "sample.pdf"
    pdf_content = b"dummy pdf content"
    pdf_path.write_bytes(pdf_content)

    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.pdf",
        content=pdf_content,
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".pdf")
    assert candidate.ai_content == pdf_content
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False
