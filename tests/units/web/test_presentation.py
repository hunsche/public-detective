"""Unit tests for presentation service."""

from unittest.mock import MagicMock, patch

import pytest
from public_detective.models.analyses import Analysis, AnalysisResult
from public_detective.web.presentation import PresentationService


@pytest.fixture
def mock_repo():
    """Mock the analysis repository."""
    with patch("public_detective.web.presentation.AnalysisRepository") as mock:
        yield mock.return_value


@pytest.fixture
def mock_db_manager():
    """Mock the database manager."""
    with patch("public_detective.web.presentation.DatabaseManager") as mock:
        yield mock


@pytest.fixture
def service(mock_repo, mock_db_manager):
    """Create a presentation service instance."""
    return PresentationService()


def test_get_home_stats(service, mock_repo):
    """Test getting home stats."""
    mock_repo.get_home_stats.return_value = {
        "total_analyses": 10,
        "total_savings": 1000.0,
        "total_red_flags": 5,
    }
    stats = service.get_home_stats()
    assert stats["total_analyses"] == 10
    assert stats["total_savings"] == "R$ 1.000,00"
    assert stats["total_red_flags"] == 5


def test_get_recent_analyses(service, mock_repo):
    """Test getting recent analyses."""
    mock_analysis = MagicMock(spec=AnalysisResult)
    mock_analysis.analysis_id = "123"
    mock_analysis.procurement_control_number = "123456"
    mock_analysis.ai_analysis = MagicMock(spec=Analysis)
    mock_analysis.ai_analysis.risk_score = 80
    mock_analysis.ai_analysis.procurement_summary = "Summary"
    mock_analysis.ai_analysis.analysis_summary = "Analysis Summary"
    mock_analysis.ai_analysis.red_flags = []
    mock_analysis.created_at = "2023-01-01"
    mock_analysis.raw_data = {}

    mock_repo.get_recent_analyses_summary.return_value = ([mock_analysis], 1)

    result = service.get_recent_analyses(page=1, limit=10)
    assert result["total"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["id"] == "123"


def test_search_analyses(service, mock_repo):
    """Test searching analyses."""
    mock_analysis = MagicMock(spec=AnalysisResult)
    mock_analysis.analysis_id = "123"
    mock_analysis.procurement_control_number = "123456"
    mock_analysis.ai_analysis = MagicMock(spec=Analysis)
    mock_analysis.ai_analysis.risk_score = 80
    mock_analysis.ai_analysis.procurement_summary = "Summary"
    mock_analysis.ai_analysis.analysis_summary = "Analysis Summary"
    mock_analysis.ai_analysis.red_flags = []
    mock_analysis.created_at = "2023-01-01"
    mock_analysis.raw_data = {}

    mock_repo.search_analyses_summary.return_value = ([mock_analysis], 1)

    result = service.search_analyses("query", page=1, limit=10)
    assert result["total"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["id"] == "123"


def test_get_analysis_details(service, mock_repo):
    """Test getting analysis details."""
    mock_repo.get_analysis_details.return_value = {
        "analysis_id": "123e4567-e89b-12d3-a456-426614174000",
        "procurement_control_number": "123456",
        "risk_score": 80,
        "risk_score_rationale": "Rationale",
        "procurement_summary": "Summary",
        "analysis_summary": "Analysis Summary",
        "red_flags": [],
        "seo_keywords": [],
        "created_at": "2023-01-01",
        "grounding_metadata": {},
        "pncp_publication_date": "2023-01-01",
        "total_estimated_value": 1000.0,
        "modality_id": 1,
        "procurement_status_id": 1,
        "raw_data": {},
    }

    result = service.get_analysis_details("123e4567-e89b-12d3-a456-426614174000")
    assert result is not None
    assert result["id"] == "123e4567-e89b-12d3-a456-426614174000"
    assert result["score"] == 80
    assert result["estimated_value"] == "R$ 1.000,00"


def test_get_analysis_details_not_found(service, mock_repo):
    """Test getting analysis details when not found."""
    mock_repo.get_analysis_details.return_value = None
    result = service.get_analysis_details("123e4567-e89b-12d3-a456-426614174000")
    assert result is None


def test_get_analysis_details_invalid_uuid(service):
    """Test getting analysis details with invalid UUID."""


def test_get_analysis_details_complex(service, mock_repo):
    """Test getting analysis details with complex data."""
    mock_repo.get_analysis_details.return_value = {
        "analysis_id": "123e4567-e89b-12d3-a456-426614174000",
        "procurement_control_number": "123456",
        "risk_score": 80,
        "risk_score_rationale": "Rationale",
        "procurement_summary": "Summary",
        "analysis_summary": "Analysis Summary",
        "red_flags": '[{"category": "SOBREPRECO", "severity": "GRAVE", "description": "Desc", "evidence_quote": "Quote", "auditor_reasoning": "Reasoning", "potential_savings": 100.0, "sources": [{"name": "Source", "type": "VAREJO", "reference_price": 10.0}]}]',
        "seo_keywords": [],
        "created_at": "2023-01-01",
        "grounding_metadata": {},
        "pncp_publication_date": "2023-01-01",
        "total_estimated_value": 1000.0,
        "modality_id": 99,  # Unknown modality
        "procurement_status_id": 99,  # Unknown status
        "raw_data": '{"unidadeOrgao": {"municipioNome": "City", "ufSigla": "UF"}, "orgaoEntidade": {"razaoSocial": "Agency", "cnpj": "123"}, "anoCompra": 2023, "sequencialCompra": 1}',
    }

    result = service.get_analysis_details("123e4567-e89b-12d3-a456-426614174000")
    assert result is not None
    assert result["modality"] == "99"
    assert result["status"] == "99"
    assert len(result["red_flags"]) == 1
    assert result["red_flags"][0]["category"] == "Sobrepreço"
    assert result["red_flags"][0]["sources"][0]["type"] == "Varejo"
    assert result["official_link"] == "https://pncp.gov.br/app/editais/123/2023/1"
