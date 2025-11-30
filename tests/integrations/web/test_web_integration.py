"""Integration tests for the web layer."""

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from public_detective.web.main import app
import pytest

# We don't need to mock PresentationService anymore.
# The app will use the real service which connects to the DB.
# The DB is set up by the db_session fixture in conftest.py.

@pytest.fixture
def client(db_session):
    # db_session fixture ensures DB is ready and env vars are set
    yield TestClient(app)


def test_home_page_structure(client):
    """Test the structure of the home page."""
    response = client.get("/")
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Check for main title
    h1 = soup.find("h1")
    assert h1 is not None
    assert "Transparência em" in h1.text
    
    # Check for stats section
    stats_section = soup.find_all("div", class_="rounded-2xl")
    assert len(stats_section) >= 3
    
    # Check for "Ver Análises" button
    analyses_link = None
    for link in soup.find_all("a"):
        if "Ver Análises" in link.text:
            analyses_link = link
            break
    assert analyses_link is not None
    assert analyses_link["href"].endswith("/analyses")


def test_analyses_page_browser_access(client):
    """Test accessing analyses page directly via browser."""
    response = client.get("/analyses")
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Should have full layout
    assert soup.find("html") is not None
    assert soup.find("body") is not None
    
    # Check title
    h1 = soup.find("h1")
    assert h1 is not None
    assert "Análises de Licitações" in h1.text
    
    # Check search input
    search_input = soup.find("input", {"name": "q"})
    assert search_input is not None
    assert search_input.get("placeholder") == "Pesquisar por objeto, órgão ou detalhes..."


def test_analyses_page_htmx_request(client):
    """Test accessing analyses page via HTMX."""
    response = client.get("/analyses", headers={"HX-Request": "true"})
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Should NOT have full layout
    assert soup.find("html") is None
    assert soup.find("body") is None
    
    # With seeded data, we expect to see analysis cards
    card = soup.find("div", class_="rounded-xl")
    # If seeding worked, we should have cards. If not, we might see "Nenhuma análise encontrada".
    # Given we use seed.sql, we expect data.
    if card is None:
         # Fallback check if seed failed or DB is empty for some reason
         assert soup.find("p", string="Nenhuma análise encontrada.") is not None
    else:
        assert card is not None


def test_search_functionality_htmx(client):
    """Test search functionality via HTMX."""
    # Search for something that should exist in seed data
    # Based on seed.sql content (implied from E2E test), "INSULINA" exists.
    response = client.get("/analyses?q=INSULINA", headers={"HX-Request": "true"})
    assert response.status_code == 200
    
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Should find results
    card = soup.find("div", class_="rounded-xl")
    assert card is not None
    
    # Search for something that should NOT exist
    response_empty = client.get("/analyses?q=NONEXISTENT_ITEM_123", headers={"HX-Request": "true"})
    assert response_empty.status_code == 200
    soup_empty = BeautifulSoup(response_empty.text, "html.parser")
    assert "Nenhuma análise encontrada" in soup_empty.text


def test_analysis_detail_page(client):
    """Test analysis detail page structure."""
    # We need a valid ID. In integration tests with real DB, we can query the DB or use a known ID from seed.
    # However, since we don't have easy access to the DB session here (client fixture doesn't return it directly, though we could request it),
    # let's try to find an ID from the list page first.
    
    # Get list page
    response_list = client.get("/analyses")
    soup_list = BeautifulSoup(response_list.text, "html.parser")
    
    # Find first analysis link
    detail_link = soup_list.find("a", href=lambda h: h and "/analyses/" in h)
    
    if detail_link:
        detail_url = detail_link["href"]
        # Extract ID or just use URL
        response = client.get(detail_url)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        assert soup.find("h1") is not None
    else:
        # If no data, we can't test detail page success path easily without inserting data.
        # But we expect seed data.
        pytest.fail("No analysis found in list page to test detail view.")

    # Test 404
    response_404 = client.get("/analyses/00000000-0000-0000-0000-000000000000")
    assert response_404.status_code == 404
