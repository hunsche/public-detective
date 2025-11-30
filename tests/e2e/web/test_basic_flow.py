import pytest
from playwright.sync_api import Page, expect


def test_homepage_loads(page: Page, live_server_url: str) -> None:
    # Assuming the app is running on localhost:8000 (needs to be started separately or via fixture)
    # For now, we might need a fixture to start the server or assume it's running.
    # Given the complexity of starting the server in tests, we might want to use a plugin or a custom fixture.
    # But for this initial step, let's just write the test structure.

    # NOTE: This test expects the server to be running.
    # In a real CI environment, we'd use pytest-xprocess or similar to start the server.
    # Or use the `live_server` fixture if using something like pytest-django/flask/fastapi-deps.

    page.goto(live_server_url)
    expect(page).to_have_title("Detetive Público - Home")

    # Navigate to the analyses page
    page.get_by_role("link", name="Ver Análises").click()
    expect(page).to_have_title("Detetive Público - Análises")

    # Verify some content from the seed data exists
    if page.get_by_text("Nenhuma análise encontrada").is_visible():
        print("DEBUG: Database appears empty. Seeding might have failed.")
        print(page.content())
        pytest.fail("Database is empty, seeding failed.")

    # Search for the specific procurement to avoid pagination issues
    # We use press_sequentially to trigger keyup events for HTMX
    search_input = page.get_by_placeholder("Pesquisar por objeto, órgão ou detalhes...")
    search_input.click()
    search_input.press_sequentially("INSULINA", delay=100)
    search_input.press("Enter")

    # Wait for HTMX to trigger and update the content
    # We wait for the specific item to appear, which implicitly waits for the search to complete

    # Check for the card by control number (which is the title in h3)
    # The control number for the insulin procurement is 60448040000122-1-000782/2025
    card = page.locator(".group").filter(has=page.locator("h3", has_text="60448040000122-1-000782/2025"))
    expect(card).to_be_visible(timeout=10000)

    # Verify that ONLY one item is presented in the listing
    # We expect exactly one card with the class 'group' (which is the card container)
    # We filter by having an h3 to ensure we are counting analysis cards
    analysis_cards = page.locator(".group").filter(has=page.locator("h3"))
    expect(analysis_cards).to_have_count(1)

    # Navigate to the detail page for this procurement
    # We find the card containing the text, then find the "Detalhes" link within it
    card.get_by_role("link", name="Detalhes").click()

    # Verify the detail page loads
    expect(page).to_have_title("Detetive Público - Detalhes da Análise")
    # The h1 is the control number
    expect(page.locator("h1").filter(has_text="60448040000122-1-000782/2025")).to_be_visible()
    # The description should be visible on the page
    expect(page.locator("body")).to_contain_text("aquisição de medicamentos diversos (Insulinas")

    # Check for a specific red flag description that should be on the detail page
    expect(page.get_by_text("Exigência de fornecimento de 9 freezers")).to_be_visible()

    # Check for the "Análises de Licitações" header
    expect(page.get_by_text("Resumo da Licitação")).to_be_visible()
