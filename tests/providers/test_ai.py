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
def mock_converter_provider():
    """Mocks the ConverterProvider."""
    with patch("providers.ai.ConverterProvider") as mock_provider:
        mock_instance = MagicMock()
        mock_provider.return_value = mock_instance
        yield mock_instance


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


def test_ai_provider_instantiation(mock_gemini_client, mock_converter_provider):
    """Tests that the AiProvider can be instantiated correctly."""
    provider = AiProvider(MockOutputSchema)
    assert provider is not None
    assert provider.converter is not None


@pytest.mark.parametrize(
    "filename, target_format",
    [
        ("test.docx", "pdf"),
        ("test.xls", "csv"),
        ("test.pdf", None),
    ],
)
def test_file_conversion_flow(
    mock_gemini_client, mock_converter_provider, filename, target_format
):
    """Tests that the correct conversion method is called for each file type."""
    mock_converter_provider.convert_file.return_value = b"converted content"

    with patch("providers.ai.ConverterProvider", return_value=mock_converter_provider):
        provider = AiProvider(MockOutputSchema)
        processed_files = provider.convert_files([(filename, b"test content")])

    if target_format:
        mock_converter_provider.convert_file.assert_called_once_with(
            b"test content", filename, target_format
        )
        assert processed_files[0][0].endswith(f".{target_format}")
    else:
        mock_converter_provider.convert_file.assert_not_called()
        assert processed_files[0][0] == filename
