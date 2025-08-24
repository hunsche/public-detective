"""
Unit tests for the AnalysisService.
"""
from unittest.mock import MagicMock, patch

import pytest
from models.analysis import Analysis
from models.procurement import Procurement
from services.analysis import AnalysisService


@pytest.fixture
def mock_ai_provider():
    """Mocks the AiProvider."""
    with patch("services.analysis.AiProvider") as mock_provider:
        yield mock_provider


@pytest.fixture
def mock_gcs_provider():
    """Mocks the GcsProvider."""
    with patch("services.analysis.GcsProvider") as mock_provider:
        yield mock_provider


@pytest.fixture
def mock_analysis_repo():
    """Mocks the AnalysisRepository."""
    with patch("services.analysis.AnalysisRepository") as mock_repo:
        yield mock_repo


@pytest.fixture
def mock_procurement_repo():
    """Mocks the ProcurementRepository."""
    with patch("services.analysis.ProcurementRepository") as mock_repo:
        yield mock_repo


def test_analysis_service_instantiation(
    mock_ai_provider, mock_gcs_provider, mock_analysis_repo, mock_procurement_repo
):
    """Tests that the AnalysisService can be instantiated correctly."""
    service = AnalysisService()
    assert service is not None


def test_idempotency_check(mock_procurement_repo, mock_analysis_repo, mock_ai_provider):
    """Tests that analysis is skipped if a result with the same hash exists."""
    mock_procurement_repo.return_value.process_procurement_documents.return_value = (
        [("file.pdf", b"content")], [("file.pdf", b"content")]
    )
    mock_analysis_repo.return_value.get_analysis_by_hash.return_value = "existing"

    service = AnalysisService()
    procurement = Procurement(pncp_control_number="123", year=2025, mode="test", status="test", object="test", url="http://test.com")

    service.analyze_procurement(procurement)

    mock_ai_provider.return_value.get_structured_analysis.assert_not_called()
