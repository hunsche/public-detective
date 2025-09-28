"""Unit tests for the AnalysisService."""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.models.analyses import Analysis
from public_detective.models.procurements import Procurement
from public_detective.repositories.procurements import ProcessedFile
from public_detective.services.analysis import AIFileCandidate, AnalysisService


@pytest.fixture
def mock_dependencies() -> dict[str, Any]:
    """Fixture to create mock dependencies for the AnalysisService."""
    return {
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


def test_analyze_procurement_happy_path(mock_dependencies: dict[str, Any], mock_procurement: Procurement) -> None:
    """Test the happy path for analyze_procurement."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        raw_document_metadata={"titulo": "Edital"},
        relative_path="file.pdf",
        content=b"content",
    )
    service.procurement_repo.process_procurement_documents.return_value = [processed_file]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    service.source_document_repo.save_source_document.return_value = uuid4()  # Return a real UUID
    mock_ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
        seo_keywords=["keyword1"],
    )
    service.ai_provider.get_structured_analysis.return_value = (mock_ai_analysis, 100, 50, 10)

    with patch("public_detective.services.analysis.PricingService") as mock_pricing_service:
        mock_pricing_service.return_value.calculate.return_value = (
            Decimal("1"),
            Decimal("2"),
            Decimal("0.5"),
            Decimal("3.5"),
        )
        service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)
        service.analyze_procurement(mock_procurement, 1, analysis_id)

    service.analysis_repo.save_analysis.assert_called_once()


def test_analyze_procurement_no_files(mock_dependencies: dict[str, Any], mock_procurement: Procurement) -> None:
    """Test analyze_procurement when no files are found."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = []

    service.analyze_procurement(mock_procurement, 1, uuid4())

    service.analysis_repo.save_analysis.assert_not_called()


def test_build_analysis_prompt(mock_dependencies: dict[str, Any], mock_procurement: Procurement) -> None:
    """Test that the _build_analysis_prompt method constructs the correct prompt."""
    service = AnalysisService(**mock_dependencies)
    candidates = [
        AIFileCandidate(
            synthetic_id=str(uuid4()),
            raw_document_metadata={
                "titulo": "Edital",
                "tipoDocumentoNome": "Edital",
                "dataPublicacaoPncp": "2025-01-01T00:00:00",
            },
            original_path="edital.pdf",
            original_content=b"",
            is_included=True,
        )
    ]
    prompt = service._build_analysis_prompt(mock_procurement, candidates, ["Warning 1"])
    assert "Edital" in prompt
    assert "Warning 1" in prompt
    assert "CONTEXTO DOS DOCUMENTOS ANEXADOS" in prompt
