from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from google.genai import types
from public_detective.providers.ai import AiProvider
from pydantic import BaseModel, Field
from pytest import MonkeyPatch


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
def mock_ai_provider(monkeypatch: MonkeyPatch) -> Generator[tuple[MagicMock, MagicMock, MagicMock], None, None]:
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    with (
        patch("public_detective.providers.ai.genai.Client") as mock_genai_client,
        patch("public_detective.providers.ai.GcsProvider") as mock_gcs_provider,
        patch("public_detective.providers.ai.ConfigProvider") as mock_config_provider,
    ):
        mock_client_instance = MagicMock()
        mock_gcs_instance = MagicMock()
        mock_config_instance = MagicMock()

        # This simulates the chained calls like client.models.generate_content
        mock_models_api = MagicMock()
        mock_client_instance.models = mock_models_api
        mock_genai_client.return_value = mock_client_instance

        mock_gcs_provider.return_value = mock_gcs_instance
        mock_config_provider.get_config.return_value = mock_config_instance

        mock_config_instance.GCP_GCS_BUCKET_PROCUREMENTS = "test-bucket"
        mock_config_instance.GCP_PROJECT = "test-project"
        mock_config_instance.GCP_LOCATION = "us-central1"
        mock_config_instance.GCP_GEMINI_MODEL = "gemini-test"

        # Yield the mock for the 'models' attribute, which is what's used in the provider
        yield mock_models_api, mock_gcs_instance, mock_config_instance


def create_mock_response(text: str, prompt_token_count: int, candidates_token_count: int) -> MagicMock:
    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_content = MagicMock()

    # The text is nested inside a Part inside a Content inside a Candidate
    mock_part = MagicMock()
    mock_part.text = text
    mock_content.parts = [mock_part]
    mock_candidate.content = mock_content
    mock_response.candidates = [mock_candidate]

    # Mock the usage_metadata
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = prompt_token_count
    mock_usage.candidates_token_count = candidates_token_count
    mock_response.usage_metadata = mock_usage

    # Add a mock for the text property for direct access
    type(mock_response).text = text

    return mock_response


def test_get_structured_analysis(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, mock_gcs_instance, _ = mock_ai_provider

    mock_response = create_mock_response(
        text="""{"risk_score": 8, "summary": "Test summary"}""",
        prompt_token_count=10,
        candidates_token_count=20,
    )
    mock_models_api.generate_content.return_value = mock_response

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
    mock_models_api.generate_content.assert_called_once()


def test_get_structured_analysis_with_max_tokens(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _ = mock_ai_provider

    mock_response = create_mock_response(
        text="""{"risk_score": 8, "summary": "Test summary"}""",
        prompt_token_count=0,
        candidates_token_count=0,
    )
    mock_models_api.generate_content.return_value = mock_response

    ai_provider = AiProvider(output_schema=MockOutputSchema)
    ai_provider.get_structured_analysis(prompt="test prompt", files=[], max_output_tokens=500)

    _, kwargs = mock_models_api.generate_content.call_args
    generation_config = kwargs.get("config")
    assert generation_config.max_output_tokens == 500


def test_get_structured_analysis_uses_valid_schema(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _ = mock_ai_provider
    mock_models_api.generate_content.return_value = create_mock_response(
        text="""{
            "risk_score": 8,
            "risk_score_rationale": "High risk",
            "summary": "Test summary",
            "red_flags": [],
            "seo_keywords": []
        }""",
        prompt_token_count=0,
        candidates_token_count=0,
    )

    ai_provider = AiProvider(output_schema=AnalysisWithValidation)
    ai_provider.get_structured_analysis(prompt="test prompt", files=[])

    _, kwargs = mock_models_api.generate_content.call_args
    generation_config = kwargs.get("config")

    assert generation_config.response_schema is AnalysisWithValidation


def test_parse_response_blocked(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = create_mock_response(text="", prompt_token_count=0, candidates_token_count=0)
    mock_response.candidates = []
    mock_response.prompt_feedback.block_reason.name = "SAFETY"

    with pytest.raises(ValueError, match="AI model blocked the response"):
        ai_provider._parse_and_validate_response(mock_response)


def test_parse_response_empty(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = create_mock_response(text="", prompt_token_count=0, candidates_token_count=0)
    mock_response.candidates = []
    mock_response.prompt_feedback = None

    with pytest.raises(ValueError, match="AI model returned an empty response"):
        ai_provider._parse_and_validate_response(mock_response)


def test_parse_response_from_text(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = create_mock_response(
        text="""{"risk_score": 5, "summary": "text summary"}""",
        prompt_token_count=0,
        candidates_token_count=0,
    )

    result = ai_provider._parse_and_validate_response(mock_response)

    assert isinstance(result, MockOutputSchema)
    assert result.risk_score == 5
    assert result.summary == "text summary"


def test_parse_response_with_markdown_in_text(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = create_mock_response(
        text="""```json
{"risk_score": 5, "summary": "text summary"}
```""",
        prompt_token_count=0,
        candidates_token_count=0,
    )

    result = ai_provider._parse_and_validate_response(mock_response)
    assert isinstance(result, MockOutputSchema)


def test_parse_response_parsing_error(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = create_mock_response(text="this is not json", prompt_token_count=0, candidates_token_count=0)

    with pytest.raises(ValueError, match="could not be parsed"):
        ai_provider._parse_and_validate_response(mock_response)


def test_upload_file_to_gcs(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, mock_gcs_instance, _ = mock_ai_provider
    mock_gcs_instance.upload_file.return_value = "gs://test-bucket/ai-uploads/some-uuid/test.pdf"

    ai_provider = AiProvider(MockOutputSchema)
    gcs_uri = ai_provider._upload_file_to_gcs(b"content", "test.pdf")

    assert "gs://test-bucket/ai-uploads/" in gcs_uri
    assert gcs_uri.endswith("/test.pdf")
    mock_gcs_instance.upload_file.assert_called_once()


def test_count_tokens_for_analysis(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _ = mock_ai_provider

    mock_models_api.count_tokens.return_value = types.CountTokensResponse(total_tokens=123)

    ai_provider = AiProvider(MockOutputSchema)
    prompt = "test prompt"
    files = [("file1.pdf", b"content1"), ("file2.txt", b"content2")]

    token_count, _ = ai_provider.count_tokens_for_analysis(prompt, files)

    assert token_count == 123
    mock_models_api.count_tokens.assert_called_once()
    _, kwargs = mock_models_api.count_tokens.call_args
    contents = kwargs["contents"]
    assert isinstance(contents, types.Content)
    assert contents.role == "user"
    assert contents.parts is not None
    assert len(contents.parts) == 3
    assert contents.parts[0].text == prompt
    assert contents.parts[1].file_data is not None
    assert contents.parts[1].file_data.mime_type == "application/pdf"
    assert contents.parts[1].file_data.file_uri is not None
    assert "gs://" in contents.parts[1].file_data.file_uri
    assert contents.parts[2].file_data is not None
    assert contents.parts[2].file_data.mime_type == "text/plain"
    assert contents.parts[2].file_data.file_uri is not None
    assert "gs://" in contents.parts[2].file_data.file_uri
