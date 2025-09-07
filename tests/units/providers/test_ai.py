import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from source.providers.ai import AiProvider


class MockOutputSchema(BaseModel):
    risk_score: int
    summary: str


# The order of decorators is bottom-up. The arguments to the test function match this order.
@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_ai_provider_instantiation(mock_auth, mock_init, mock_gen_model):
    """Tests that the AiProvider can be instantiated correctly."""
    # Act
    provider = AiProvider(MockOutputSchema)

    # Assert
    assert provider is not None
    mock_init.assert_called_once()
    mock_gen_model.assert_called_once()


@patch("source.providers.ai.vertexai.init", side_effect=Exception("Auth error"))
def test_ai_provider_init_failure(mock_init):
    """Tests that AiProvider raises ValueError if vertexai.init fails."""
    with pytest.raises(ValueError, match="Failed to initialize Vertex AI"):
        AiProvider(MockOutputSchema)


@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_get_structured_analysis(mock_auth, mock_init, mock_gen_model):
    """Tests a successful call to get_structured_analysis."""
    # Arrange
    mock_model_instance = mock_gen_model.return_value
    mock_response = MagicMock()
    mock_response.text = json.dumps({"risk_score": 8, "summary": "Test summary"})
    mock_response.usage_metadata.prompt_token_count = 100
    mock_response.usage_metadata.candidates_token_count = 50
    mock_model_instance.generate_content.return_value = mock_response

    provider = AiProvider(output_schema=MockOutputSchema)
    gcs_uris = ["gs://bucket/file1.pdf"]

    # Act
    result, _, _ = provider.get_structured_analysis(prompt="test prompt", gcs_uris=gcs_uris)

    # Assert
    assert isinstance(result, MockOutputSchema)
    assert result.risk_score == 8
    mock_model_instance.generate_content.assert_called_once()
    args, _ = mock_model_instance.generate_content.call_args
    contents = args[0]
    assert contents[1].to_dict()["file_data"]["file_uri"] == "gs://bucket/file1.pdf"


@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_get_structured_analysis_with_max_tokens(mock_auth, mock_init, mock_gen_model):
    """Should include max_output_tokens in the generation_config when provided."""
    mock_model_instance = mock_gen_model.return_value
    mock_response = MagicMock(text=json.dumps({"risk_score": 0, "summary": ""}))
    mock_model_instance.generate_content.return_value = mock_response

    provider = AiProvider(output_schema=MockOutputSchema)
    provider.get_structured_analysis(prompt="test", gcs_uris=[], max_output_tokens=500)

    _, kwargs = mock_model_instance.generate_content.call_args
    generation_config = kwargs.get("generation_config")
    assert generation_config is not None
    config_dict = generation_config.to_dict()
    assert config_dict.get("max_output_tokens") == 500


@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_count_tokens_for_analysis(mock_auth, mock_init, mock_gen_model):
    """Tests that count_tokens_for_analysis works correctly."""
    mock_model_instance = mock_gen_model.return_value
    mock_model_instance.count_tokens.return_value = MagicMock(total_tokens=123)

    provider = AiProvider(MockOutputSchema)
    token_count, _ = provider.count_tokens_for_analysis("prompt", [("f.pdf", b"c")])

    assert token_count == 123
    mock_model_instance.count_tokens.assert_called_once()


@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_parse_response_blocked(mock_auth, mock_init, mock_gen_model):
    """Tests that a ValueError is raised if the response is blocked."""
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates = []
    mock_response.prompt_feedback.block_reason.name = "SAFETY"

    with pytest.raises(ValueError, match="AI model blocked the response"):
        provider._parse_and_validate_response(mock_response)


@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_parse_response_empty(mock_auth, mock_init, mock_gen_model):
    """Tests that a ValueError is raised if the response has no candidates."""
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates = []
    mock_response.prompt_feedback = None

    with pytest.raises(ValueError, match="AI model returned an empty response"):
        provider._parse_and_validate_response(mock_response)


@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_parse_response_from_text(mock_auth, mock_init, mock_gen_model):
    """Tests parsing a valid response from the text field."""
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.text = '```json\n{"risk_score": 5, "summary": "text summary"}\n```'

    result = provider._parse_and_validate_response(mock_response)
    assert isinstance(result, MockOutputSchema)
    assert result.risk_score == 5


@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_parse_response_from_function_call(mock_auth, mock_init, mock_gen_model):
    """Tests parsing a valid response from the function_call field as a fallback."""
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.text = "invalid json"
    mock_function_call = MagicMock()
    mock_function_call.name = "MockOutputSchema"
    mock_function_call.args = {"risk_score": 7, "summary": "function call summary"}
    mock_response.candidates = [MagicMock(content=MagicMock(parts=[MagicMock(function_call=mock_function_call)]))]

    result = provider._parse_and_validate_response(mock_response)
    assert isinstance(result, MockOutputSchema)
    assert result.risk_score == 7


@patch("source.providers.ai.GenerativeModel")
@patch("source.providers.ai.vertexai.init")
@patch("google.auth.default", return_value=(MagicMock(), "test-project"))
def test_parse_response_parsing_error(mock_auth, mock_init, mock_gen_model):
    """Tests that a ValueError is raised if the response cannot be parsed."""
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.text = "this is not json"
    mock_response.candidates = [MagicMock(content=MagicMock(parts=[MagicMock(function_call=None)]))]

    with pytest.raises(ValueError, match="could not be parsed"):
        provider._parse_and_validate_response(mock_response)
