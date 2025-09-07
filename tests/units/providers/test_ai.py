from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from models.analyses import Analysis
from providers.ai import AiProvider
from pydantic import BaseModel, Field
from vertexai.generative_models import GenerationConfig, Part


class MockOutputSchema(BaseModel):
    risk_score: int
    summary: str


class AnalysisWithValidation(BaseModel):
    risk_score: int = Field(..., ge=0, le=10)
    risk_score_rationale: str
    summary: str
    red_flags: list[str]
    seo_keywords: list[str]


@pytest.fixture
def mock_ai_provider(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    with (
        patch("providers.ai.vertexai.init"),
        patch("providers.ai.aiplatform.init"),
        patch("providers.ai.GenerativeModel") as mock_gen_model,
        patch("providers.ai.GcsProvider") as mock_gcs_provider,
        patch("providers.ai.ConfigProvider") as mock_config_provider,
    ):

        mock_model_instance = MagicMock()
        mock_gcs_instance = MagicMock()
        mock_config_instance = MagicMock()

        mock_gen_model.return_value = mock_model_instance
        mock_gcs_provider.return_value = mock_gcs_instance
        mock_config_provider.get_config.return_value = mock_config_instance

        mock_config_instance.GCP_VERTEX_AI_BUCKET = "test-bucket"
        mock_config_instance.GCP_PROJECT = "test-project"
        mock_config_instance.GCP_LOCATION = "us-central1"
        mock_config_instance.GCP_GEMINI_MODEL = "gemini-test"

        yield mock_model_instance, mock_gcs_instance, mock_config_instance


def test_get_structured_analysis(mock_ai_provider):
    mock_model_instance, mock_gcs_instance, _ = mock_ai_provider

    mock_response = MagicMock()
    mock_response.text = """{"risk_score": 8, "summary": "Test summary"}"""
    mock_response.usage_metadata.prompt_token_count = 10
    mock_response.usage_metadata.candidates_token_count = 20
    mock_model_instance.generate_content.return_value = mock_response

    mock_gcs_instance.upload_file.return_value = "gs://test-bucket/ai-uploads/some-uuid/file1.pdf"

    ai_provider = AiProvider(output_schema=MockOutputSchema)
    result, input_tokens, output_tokens = ai_provider.get_structured_analysis(
        prompt="test prompt", files=[("file1.pdf", b"content")]
    )

    assert isinstance(result, MockOutputSchema)
    assert result.risk_score == 8
    assert input_tokens == 10
    assert output_tokens == 20
    mock_gcs_instance.upload_file.assert_called_once()
    mock_model_instance.generate_content.assert_called_once()


def test_get_structured_analysis_with_max_tokens(mock_ai_provider):
    mock_model_instance, _, _ = mock_ai_provider

    # We need to return a mock from the generate_content call
    mock_response = MagicMock()
    mock_response.text = """{"risk_score": 8, "summary": "Test summary"}"""
    mock_response.usage_metadata.prompt_token_count = 0
    mock_response.usage_metadata.candidates_token_count = 0
    mock_model_instance.generate_content.return_value = mock_response

    ai_provider = AiProvider(output_schema=MockOutputSchema)
    ai_provider.get_structured_analysis(prompt="test prompt", files=[], max_output_tokens=500)

    _, kwargs = mock_model_instance.generate_content.call_args
    generation_config = kwargs.get("generation_config")
    assert generation_config._raw_generation_config.max_output_tokens == 500


def test_get_structured_analysis_uses_valid_schema(mock_ai_provider):
    mock_model_instance, _, _ = mock_ai_provider
    mock_model_instance.generate_content.return_value = MagicMock(
        text="""{"risk_score": 8, "risk_score_rationale": "High risk", "summary": "Test summary", "red_flags": [], "seo_keywords": []}""",
        usage_metadata=MagicMock(prompt_token_count=0, candidates_token_count=0),
    )

    # Using the simplified schema for the test
    ai_provider = AiProvider(output_schema=AnalysisWithValidation)
    ai_provider.get_structured_analysis(prompt="test prompt", files=[])

    _, kwargs = mock_model_instance.generate_content.call_args
    generation_config = kwargs.get("generation_config")
    response_schema = generation_config._raw_generation_config.response_schema

    assert response_schema is not None
    risk_score_properties = response_schema.properties["risk_score"]
    with pytest.raises(AttributeError):
        _ = risk_score_properties.ge
    with pytest.raises(AttributeError):
        _ = risk_score_properties.le


def test_parse_response_blocked(mock_ai_provider):
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates = []
    mock_response.prompt_feedback.block_reason.name = "SAFETY"

    with pytest.raises(ValueError, match="AI model blocked the response"):
        ai_provider._parse_and_validate_response(mock_response)


def test_parse_response_empty(mock_ai_provider):
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.candidates = []
    mock_response.prompt_feedback = None

    with pytest.raises(ValueError, match="AI model returned an empty response"):
        ai_provider._parse_and_validate_response(mock_response)


def test_parse_response_from_text(mock_ai_provider):
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.text = """{"risk_score": 5, "summary": "text summary"}"""

    result = ai_provider._parse_and_validate_response(mock_response)

    assert isinstance(result, MockOutputSchema)
    assert result.risk_score == 5
    assert result.summary == "text summary"


def test_parse_response_with_markdown_in_text(mock_ai_provider):
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.text = """```json
{"risk_score": 5, "summary": "text summary"}
```"""

    result = ai_provider._parse_and_validate_response(mock_response)
    assert isinstance(result, MockOutputSchema)


def test_parse_response_parsing_error(mock_ai_provider):
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = MagicMock()
    mock_response.text = "this is not json"

    with pytest.raises(ValueError, match="could not be parsed"):
        ai_provider._parse_and_validate_response(mock_response)


def test_upload_file_to_gcs(mock_ai_provider):
    _, mock_gcs_instance, _ = mock_ai_provider
    mock_gcs_instance.upload_file.return_value = "gs://test-bucket/ai-uploads/some-uuid/test.pdf"

    ai_provider = AiProvider(MockOutputSchema)
    gcs_uri = ai_provider._upload_file_to_gcs(b"content", "test.pdf")

    assert "gs://test-bucket/ai-uploads/" in gcs_uri
    assert gcs_uri.endswith("/test.pdf")
    mock_gcs_instance.upload_file.assert_called_once()


def test_count_tokens_for_analysis(mock_ai_provider):
    mock_model_instance, _, _ = mock_ai_provider
    mock_model_instance.count_tokens.return_value = MagicMock(total_tokens=123)

    ai_provider = AiProvider(MockOutputSchema)
    prompt = "test prompt"
    files = [("file1.pdf", b"content1"), ("file2.txt", b"content2")]

    token_count, _ = ai_provider.count_tokens_for_analysis(prompt, files)

    assert token_count == 123
    mock_model_instance.count_tokens.assert_called_once()
    args, _ = mock_model_instance.count_tokens.call_args
    contents = args[0]
    assert len(contents) == 3
    assert contents[0] == prompt
    assert isinstance(contents[1], Part)
    assert contents[1]._raw_part.inline_data.mime_type == "application/pdf"
    assert contents[2]._raw_part.inline_data.mime_type == "text/plain"
