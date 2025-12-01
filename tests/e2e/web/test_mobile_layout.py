import pytest
from playwright.sync_api import Page, expect

def test_mobile_header_layout(page: Page, live_server_url: str) -> None:
    """Verifies that the responsive layout works correctly on mobile devices."""

    # 1. Set viewport to a mobile size (e.g., iPhone SE)
    # The collision happens on small screens, so 375px is a good test case.
    page.set_viewport_size({"width": 375, "height": 667})
    page.goto(live_server_url)

    # 2. Check that "Início" link is HIDDEN on mobile
    # We look for the link with text "Início".
    # Since we added 'hidden md:block', it should be effectively invisible.
    inicio_link = page.get_by_role("link", name="Início", exact=True)
    expect(inicio_link).not_to_be_visible()

    # 3. Check that "Análises" link is VISIBLE on mobile
    # Use exact=True to avoid matching "Ver Análises" button in the hero section
    analises_link = page.get_by_role("link", name="Análises", exact=True)
    expect(analises_link).to_be_visible()

    # 4. Check that the "Detetive Público" title is VISIBLE
    # And we expect the logo image to be visible too.
    title = page.locator("span", has_text="Detetive Público").first
    expect(title).to_be_visible()

    # 5. Switch to Desktop size
    page.set_viewport_size({"width": 1024, "height": 768})

    # 6. Check that "Início" reappears
    expect(inicio_link).to_be_visible()
