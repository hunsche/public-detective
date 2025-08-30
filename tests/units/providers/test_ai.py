from unittest.mock import MagicMock, patch

import pytest
from models.analysis import Analysis
from providers.ai import AiProvider
from pydantic import BaseModel


class MockOutputSchema(BaseModel):
    risk_score: int
    summary: str


@patch("google.generativeai.GenerativeModel")
@patch("google.generativeai.configure")
def test_get_structured_analysis_uses_valid_schema(mock_configure, mock_gen_model, monkeypatch):  # noqa: F841
    """
    Should generate content with a response schema compatible with the Gemini API,
    ensuring Pydantic validation fields like 'ge' and 'le' are not present.
    """
    # Arrange
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "fake-api-key")
    monkeypatch.setenv("GCP_GEMINI_MODEL", "gemini-test")

    # Mock the model's response to simulate a function call
    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    mock_function_call = MagicMock()
    mock_function_call.args = {
        "risk_score": 8,
        "risk_score_rationale": "High risk",
        "summary": "Test summary",
        "red_flags": [],
    }
    # This simulates the nested structure response.candidates[0].content.parts[0].function_call
    mock_response.candidates = [MagicMock()]
    mock_response.candidates[0].content.parts = [MagicMock()]
    mock_response.candidates[0].content.parts[0].function_call = mock_function_call
    mock_model_instance.generate_content.return_value = mock_response
    mock_gen_model.return_value = mock_model_instance

    ai_provider = AiProvider(output_schema=Analysis)

    # Act
    ai_provider.get_structured_analysis(prompt="test prompt", files=[])

    # Assert
    mock_model_instance.generate_content.assert_called_once()
    _, kwargs = mock_model_instance.generate_content.call_args

    # Check the generation_config for the response_schema
    generation_config = kwargs.get("generation_config")
    assert generation_config is not None
    response_schema = generation_config.response_schema

    assert response_schema is not None

    # The core of the test: ensure no invalid fields like 'ge' or 'le' are in the schema
    # We inspect the 'risk_score' property in the schema definition.
    schema_dict = response_schema.model_json_schema()
    risk_score_properties = schema_dict["properties"]["risk_score"]
    assert "ge" not in risk_score_properties
    assert "le" not in risk_score_properties


@pytest.fixture
def mock_gemini_client(monkeypatch):
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    with patch("google.generativeai.GenerativeModel") as mock_gen_model:
        yield mock_gen_model


@pytest.mark.usefixtures("mock_gemini_client")
def test_ai_provider_instantiation(monkeypatch):
    """Tests that the AiProvider can be instantiated correctly."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    provider = AiProvider(MockOutputSchema)
    assert provider is not None


def test_ai_provider_missing_api_key(monkeypatch):
    """Tests that AiProvider raises ValueError if the API key is missing."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "")
    with pytest.raises(ValueError, match="GCP_GEMINI_API_KEY must be configured"):
        AiProvider(MockOutputSchema)


@patch("google.generativeai.delete_file")
@patch("google.generativeai.upload_file")
@patch("google.generativeai.get_file")
def test_get_structured_analysis_cleans_up_files(
    mock_get_file, mock_upload_file, mock_delete_file, mock_gemini_client, monkeypatch
):
    """Tests that uploaded files are deleted even if analysis fails."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.side_effect = Exception("API failure")
    mock_gemini_client.return_value = mock_model_instance

    mock_uploaded_file = MagicMock()
    mock_uploaded_file.name = "uploaded-file-name"
    mock_uploaded_file.state.name = "ACTIVE"
    mock_upload_file.return_value = mock_uploaded_file
    mock_get_file.return_value = mock_uploaded_file

    provider = AiProvider(MockOutputSchema)
    files_to_upload = [("file1.pdf", b"content1")]

    with pytest.raises(Exception, match="API failure"):
        provider.get_structured_analysis(prompt="test", files=files_to_upload)

    mock_upload_file.assert_called_once()
    mock_delete_file.assert_called_once_with("uploaded-file-name")


@patch("google.generativeai.upload_file")
@patch("google.generativeai.get_file")
def test_upload_file_to_gemini_waits_for_active(mock_get_file, mock_upload_file, monkeypatch):
    """Tests that the upload method waits for the file to become active."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")

    processing_file = MagicMock()
    processing_file.name = "file-id"
    processing_file.state.name = "PROCESSING"

    active_file = MagicMock()
    active_file.name = "file-id"
    active_file.state.name = "ACTIVE"

    mock_upload_file.return_value = processing_file
    mock_get_file.side_effect = [processing_file, active_file]

    provider = AiProvider(MockOutputSchema)
    with patch("time.sleep"):  # Avoid actual sleeping
        result = provider._upload_file_to_gemini(b"content", "test.pdf")

    assert result == active_file
    assert mock_get_file.call_count == 2


def test_parse_response_blocked(monkeypatch):
    """Tests that a ValueError is raised if the response is blocked."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates = []
    mock_response.prompt_feedback.block_reason.name = "SAFETY"

    with pytest.raises(ValueError, match="AI model blocked the response"):
        provider._parse_and_validate_response(mock_response)


def test_parse_response_empty(monkeypatch):
    """Tests that a ValueError is raised if the response has no candidates."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates = []
    mock_response.prompt_feedback = None

    with pytest.raises(ValueError, match="AI model returned an empty response"):
        provider._parse_and_validate_response(mock_response)


def test_parse_response_from_text(monkeypatch):
    """Tests parsing a valid response from the text field."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates[0].content.parts[0].function_call = None
    mock_response.text = '```json\n{"risk_score": 5, "summary": "text summary"}\n```'

    result = provider._parse_and_validate_response(mock_response)

    assert isinstance(result, MockOutputSchema)
    assert result.risk_score == 5
    assert result.summary == "text summary"


def test_parse_response_parsing_error(monkeypatch):
    """Tests that a ValueError is raised if the response cannot be parsed."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates[0].content.parts[0].function_call = None
    mock_response.text = "this is not json"

    with pytest.raises(ValueError, match="could not be parsed"):
        provider._parse_and_validate_response(mock_response)


@patch("google.generativeai.upload_file", side_effect=Exception("Upload failed"))
def test_upload_file_to_gemini_upload_error(mock_upload_file, monkeypatch):
    """Tests that an exception during upload is caught and re-raised."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    provider = AiProvider(MockOutputSchema)

    with pytest.raises(Exception, match="Upload failed"):
        provider._upload_file_to_gemini(b"content", "test.pdf")


@patch("google.generativeai.upload_file")
@patch("google.generativeai.get_file")
def test_upload_file_to_gemini_processing_failed(mock_get_file, mock_upload_file, monkeypatch):
    """Tests that an exception is raised if the file processing fails."""
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")

    failed_file = MagicMock()
    failed_file.name = "file-id"
    failed_file.state.name = "FAILED"

    mock_upload_file.return_value = failed_file

    provider = AiProvider(MockOutputSchema)
    with pytest.raises(Exception, match="failed processing"):
        provider._upload_file_to_gemini(b"content", "test.pdf")


def test_count_tokens_for_analysis(mock_gemini_client, monkeypatch):
    """
    Tests that count_tokens_for_analysis correctly formats the request
    and returns the token count.
    """
    # Arrange
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.total_tokens = 123
    mock_model_instance.count_tokens.return_value = mock_response
    mock_gemini_client.return_value = mock_model_instance

    provider = AiProvider(MockOutputSchema)
    prompt = "test prompt"
    files = [("file1.pdf", b"content1"), ("file2.txt", b"content2")]

    # Act
    token_count = provider.count_tokens_for_analysis(prompt, files)

    # Assert
    assert token_count == 123
    mock_model_instance.count_tokens.assert_called_once()
    args, _ = mock_model_instance.count_tokens.call_args
    contents = args[0]
    assert len(contents) == 3  # prompt + 2 files
    assert contents[0] == prompt
    assert contents[1]["mime_type"] == "application/pdf"
    assert contents[1]["data"] == b"content1"
    assert contents[2]["mime_type"] == "text/plain"
    assert contents[2]["data"] == b"content2"
