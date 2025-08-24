"""
Unit tests for the AiProvider.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from providers.ai import AiProvider


class MockOutputSchema(BaseModel):
    """A mock Pydantic model for testing."""
    message: str


@pytest.fixture
def mock_gemini_client():
    """Mocks the Gemini API client."""
    with patch("providers.ai.genai") as mock_genai:
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "test_file"
        mock_uploaded_file.state = MagicMock(name="ACTIVE")
        mock_uploaded_file.state.name = "ACTIVE"
        mock_genai.upload_file.return_value = mock_uploaded_file
        mock_genai.get_file.return_value = mock_uploaded_file

        mock_response = MagicMock()
        mock_response.candidates = [MagicMock()]
        mock_response.candidates[0].content.parts[0].function_call.args = {"message": "test"}
        mock_model.generate_content.return_value = mock_response
        yield mock_genai


def test_ai_provider_instantiation(mock_gemini_client):
    """Tests that the AiProvider can be instantiated correctly."""
    provider = AiProvider(MockOutputSchema)
    assert provider is not None
