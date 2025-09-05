from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from source.models.analyses import Analysis
from source.providers.ai import AiProvider


class MockOutputSchema(BaseModel):
    risk_score: int
    summary: str


@pytest.fixture(autouse=True)
def mock_google_auth(monkeypatch):
    """Mocks google.auth.default to prevent actual credential loading."""
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    with patch("google.auth.default", return_value=(MagicMock(), "test-project")):
        yield


def test_get_structured_analysis_with_max_tokens(monkeypatch):
    """
    Should include max_output_tokens in the generation_config when provided.
    """
    # Arrange
    monkeypatch.setenv("GCP_GEMINI_MODEL", "gemini-test")
    ai_provider = AiProvider(output_schema=MockOutputSchema)

    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    mock_function_call = MagicMock()
    mock_function_call.args = {"risk_score": 8, "summary": "Test summary"}
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[0].content.parts = [MagicMock()]
    mock_response.candidates[0].content.parts[0].function_call = mock_function_call
    mock_model_instance.generate_content.return_value = mock_response
    mock_model_instance.count_tokens.return_value.total_tokens = 10
    ai_provider.model = mock_model_instance

    # Act
    ai_provider.get_structured_analysis(prompt="test prompt", files=[], max_output_tokens=500)

    # Assert
    mock_model_instance.generate_content.assert_called_once()
    _, kwargs = mock_model_instance.generate_content.call_args
    generation_config = kwargs.get("generation_config")
    assert generation_config is not None
    assert generation_config.to_dict()["max_output_tokens"] == 500


def test_pydantic_schema_is_valid_for_function_calling():
    """
    Ensures the Pydantic schema for Analysis does not contain validation fields
    that are incompatible with the Vertex AI function calling schema,
    such as 'ge' or 'le' for number validation.
    """
    schema_dict = Analysis.model_json_schema()

    # The core of the test: ensure no invalid fields like 'ge' or 'le' are in the schema
    # We inspect the 'risk_score' property in the schema definition.
    risk_score_properties = schema_dict["properties"]["risk_score"]
    assert "ge" not in risk_score_properties
    assert "le" not in risk_score_properties


def test_ai_provider_instantiation(monkeypatch):
    """Tests that the AiProvider can be instantiated correctly."""
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    with patch("vertexai.generative_models.GenerativeModel"):
        provider = AiProvider(MockOutputSchema)
        assert provider is not None


def test_parse_response_no_function_call(monkeypatch):
    """Tests that a ValueError is raised if the response has no function call."""
    monkeypatch.setenv("GCP_GEMINI_MODEL", "gemini-test")
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates[0].content.parts[0].function_call = None

    with pytest.raises(ValueError, match="Model did not return a function call"):
        provider._parse_and_validate_response(mock_response)


def test_count_tokens_for_analysis(monkeypatch):
    """
    Tests that count_tokens_for_analysis correctly formats the request
    and returns the token count.
    """
    monkeypatch.setenv("GCP_GEMINI_MODEL", "gemini-test")
    provider = AiProvider(MockOutputSchema)

    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.total_tokens = 123
    mock_model_instance.count_tokens.return_value = mock_response
    provider.model = mock_model_instance

    prompt = "test prompt"
    files = [("file1.pdf", b"content1"), ("file2.txt", b"content2")]

    token_count, _ = provider.count_tokens_for_analysis(prompt, files)

    assert token_count == 123
    mock_model_instance.count_tokens.assert_called_once()
    args, _ = mock_model_instance.count_tokens.call_args
    contents = args[0]
    assert len(contents) == 3
    assert contents[0] == prompt
    assert contents[1].mime_type == "application/pdf"
    assert contents[1].inline_data.data == b"content1"
    assert contents[2].mime_type == "text/plain"
    assert contents[2].inline_data.data == b"content2"


def test_count_tokens_for_analysis_unknown_mime_type(monkeypatch):
    """
    Tests that count_tokens_for_analysis uses a default mime type if one
    cannot be guessed.
    """
    monkeypatch.setenv("GCP_GEMINI_MODEL", "gemini-test")
    provider = AiProvider(MockOutputSchema)
    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.total_tokens = 123
    mock_model_instance.count_tokens.return_value = mock_response
    provider.model = mock_model_instance

    prompt = "test prompt"
    files = [("file_without_extension", b"content")]

    provider.count_tokens_for_analysis(prompt, files)

    mock_model_instance.count_tokens.assert_called_once()
    args, _ = mock_model_instance.count_tokens.call_args
    contents = args[0]
    assert contents[1].mime_type == "application/octet-stream"
