"""Unit tests for web pages."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from public_detective.web.main import app
from public_detective.web.presentation import PresentationService


@pytest.fixture
def mock_presentation_service():
    """Mock the presentation service."""
    return MagicMock(spec=PresentationService)


@pytest.fixture
def client(mock_presentation_service):
    """Create a test client with mocked dependencies."""
    app.dependency_overrides[PresentationService] = lambda: mock_presentation_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_home(client, mock_presentation_service):
    """Test the home page."""
    mock_presentation_service.get_home_stats.return_value = {
        "total_analyses": 10,
        "total_savings": "R$ 1.000,00",
        "total_red_flags": 5,
    }
    response = client.get("/")
    assert response.status_code == 200
    assert "Transparência em" in response.text
    assert "10" in response.text
    assert "R$ 1.000,00" in response.text


def test_analyses_list(client, mock_presentation_service):
    """Test the analyses list page."""
    mock_presentation_service.get_recent_analyses.return_value = {
        "results": [],
        "total": 0,
        "page": 1,
        "pages": 1,
        "has_next": False,
        "has_prev": False,
    }
    response = client.get("/analyses")
    assert response.status_code == 200
    assert "Análises de Licitações" in response.text


def test_analyses_search(client, mock_presentation_service):
    """Test the analyses search."""
    mock_presentation_service.search_analyses.return_value = {
        "results": [],
        "total": 0,
        "page": 1,
        "pages": 1,
        "has_next": False,
        "has_prev": False,
    }
    response = client.get("/analyses?q=test")
    assert response.status_code == 200
    mock_presentation_service.search_analyses.assert_called_once_with("test", page=1)


def test_analyses_htmx(client, mock_presentation_service):
    """Test the analyses list with HTMX request."""
    mock_presentation_service.get_recent_analyses.return_value = {
        "results": [],
        "total": 0,
        "page": 1,
        "pages": 1,
        "has_next": False,
        "has_prev": False,
    }
    response = client.get("/analyses", headers={"HX-Request": "true"})
    assert response.status_code == 200
    # Should render partial, so check for something specific to partial or absence of full layout
    # Assuming partials/analysis_list.html renders the list items
    assert "Análises de Licitações" not in response.text  # Title is in full layout
    assert "Nenhuma análise encontrada" in response.text


def test_analysis_detail(client, mock_presentation_service):
    """Test the analysis detail page."""
    mock_presentation_service.get_analysis_details.return_value = {
        "id": "123",
        "control_number": "123456",
        "score": 80,
        "summary": "Test Summary",
        "analysis_summary": "Test Analysis Summary",
        "rationale": "Test Rationale",
        "red_flags": [],
        "created_at": datetime(2023, 1, 1),
        "grounding_metadata": {},
        "location": "Test City - TS",
        "modality": "Pregão",
        "publication_date": datetime(2023, 1, 1),
        "status": "Publicada",
        "estimated_value": "R$ 1.000,00",
        "official_link": "http://example.com",
        "agency": "Test Agency",
    }
    response = client.get("/analyses/123")
    assert response.status_code == 200
    assert "Test Summary" in response.text


def test_analysis_detail_not_found(client, mock_presentation_service):
    """Test the analysis detail page when not found."""
    mock_presentation_service.get_analysis_details.return_value = None
    response = client.get("/analyses/123")
    assert response.status_code == 404
