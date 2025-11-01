"""Integration tests for the AnalysisService."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from public_detective.repositories.procurements import ProcessedFile
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def analysis_service(db_session):
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


def test_prepare_ai_candidates_specialized_image_conversion(analysis_service):
    """Tests that specialized image files are correctly converted to PNG."""
    ai_content = (Path("tests") / "fixtures" / "example.ai").read_bytes()
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="example.ai",
        content=ai_content,
        extraction_failed=False,
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".png")
    assert candidate.ai_content is not None
    assert candidate.exclusion_reason is None
