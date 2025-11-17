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
def mock_ai_provider(
    monkeypatch: MonkeyPatch,
) -> Generator[tuple[MagicMock, MagicMock, MagicMock, MagicMock], None, None]:
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    with (
        patch("public_detective.providers.ai.genai.Client") as mock_genai_client,
        patch("public_detective.providers.ai.GcsProvider") as mock_gcs_provider,
        patch("public_detective.providers.ai.ConfigProvider") as mock_config_provider,
        patch("public_detective.providers.ai.LoggingProvider") as mock_logging_provider,
    ):
        mock_client_instance = MagicMock()
        mock_gcs_instance = MagicMock()
        mock_config_instance = MagicMock()
        mock_logger_instance = MagicMock()

        mock_models_api = MagicMock()
        mock_client_instance.models = mock_models_api
        mock_genai_client.return_value = mock_client_instance

        mock_gcs_provider.return_value = mock_gcs_instance
        mock_config_provider.get_config.return_value = mock_config_instance
        mock_logging_provider.return_value.get_logger.return_value = mock_logger_instance

        mock_config_instance.GCP_GCS_BUCKET_PROCUREMENTS = "test-bucket"
        mock_config_instance.GCP_PROJECT = "test-project"
        mock_config_instance.GCP_LOCATION = "us-central1"
        mock_config_instance.GCP_GEMINI_MODEL = "gemini-test"

        yield mock_models_api, mock_gcs_instance, mock_config_instance, mock_logger_instance


def create_mock_response(
    text: str,
    prompt_token_count: int,
    candidates_token_count: int,
    thoughts_token_count: int | None = 0,
) -> MagicMock:
    mock_response = MagicMock()
    mock_candidate = MagicMock()
    mock_content = MagicMock()

    mock_part = MagicMock()
    mock_part.text = text
    mock_content.parts = [mock_part]
    mock_candidate.content = mock_content
    mock_response.candidates = [mock_candidate]

    mock_usage = MagicMock()
    mock_usage.prompt_token_count = prompt_token_count
    mock_usage.candidates_token_count = candidates_token_count
    mock_usage.thoughts_token_count = thoughts_token_count
    mock_response.usage_metadata = mock_usage

    type(mock_response).text = text

    return mock_response


def test_get_structured_analysis(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    mock_response = create_mock_response(
        text="""{"risk_score": 8, "summary": "Test summary"}""",
        prompt_token_count=10,
        candidates_token_count=20,
        thoughts_token_count=5,
    )
    mock_models_api.generate_content.return_value = mock_response

    ai_provider = AiProvider(output_schema=MockOutputSchema)
    (
        result,
        input_tokens,
        output_tokens,
        thinking_tokens,
        fallback_input_tokens,
        fallback_output_tokens,
        fallback_thinking_tokens,
    ) = ai_provider.get_structured_analysis(prompt="test prompt", file_uris=["gs://test-bucket/file1.pdf"])

    assert isinstance(result, MockOutputSchema)
    assert result.risk_score == 8
    assert input_tokens == 10
    assert output_tokens == 20
    assert thinking_tokens == 5
    assert fallback_input_tokens == 0
    assert fallback_output_tokens == 0
    assert fallback_thinking_tokens == 0
    mock_models_api.generate_content.assert_called_once()


def test_get_structured_analysis_with_max_tokens(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    mock_response = create_mock_response(
        text="""{"risk_score": 8, "summary": "Test summary"}""",
        prompt_token_count=0,
        candidates_token_count=0,
    )
    mock_models_api.generate_content.return_value = mock_response

    ai_provider = AiProvider(output_schema=MockOutputSchema)
    ai_provider.get_structured_analysis(prompt="test prompt", file_uris=[], max_output_tokens=500)

    _, kwargs = mock_models_api.generate_content.call_args
    generation_config = kwargs.get("config")
    assert generation_config.max_output_tokens == 500


def test_get_structured_analysis_uses_valid_schema(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider
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
    ai_provider.get_structured_analysis(prompt="test prompt", file_uris=[])

    _, kwargs = mock_models_api.generate_content.call_args
    generation_config = kwargs.get("config")

    assert generation_config.response_schema is AnalysisWithValidation


def test_parse_response_blocked(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = create_mock_response(text="", prompt_token_count=0, candidates_token_count=0)
    mock_response.candidates = []
    mock_response.prompt_feedback.block_reason.name = "SAFETY"

    with pytest.raises(ValueError, match="AI model blocked the response"):
        ai_provider._parse_and_validate_response(mock_response)


def test_parse_response_empty(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = create_mock_response(text="", prompt_token_count=0, candidates_token_count=0)
    mock_response.candidates = []
    mock_response.prompt_feedback = None

    with pytest.raises(ValueError, match="AI model returned an empty response"):
        ai_provider._parse_and_validate_response(mock_response)


def test_parse_response_from_text(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
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
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
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
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)
    mock_response = create_mock_response(text="this is not json", prompt_token_count=0, candidates_token_count=0)

    with pytest.raises(ValueError, match="could not be parsed"):
        ai_provider._parse_and_validate_response(mock_response)


def test_count_tokens_for_analysis(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    mock_models_api.count_tokens.return_value = types.CountTokensResponse(total_tokens=123)

    ai_provider = AiProvider(MockOutputSchema)
    prompt = "test prompt"
    file_uris = ["gs://bucket/file1.pdf", "gs://bucket/file2.txt"]

    input_tokens, output_tokens, thinking_tokens = ai_provider.count_tokens_for_analysis(prompt, file_uris)

    assert input_tokens == 123
    assert output_tokens == 0
    assert thinking_tokens == 0
    mock_models_api.count_tokens.assert_called_once()
    _, kwargs = mock_models_api.count_tokens.call_args
    request_contents = kwargs["contents"]
    assert isinstance(request_contents, types.Content)
    assert request_contents.role == "user"
    assert request_contents.parts is not None
    assert len(request_contents.parts) == 3
    assert request_contents.parts[0].text == prompt
    assert request_contents.parts[1].file_data is not None
    assert request_contents.parts[1].file_data.mime_type == "application/pdf"
    assert request_contents.parts[1].file_data.file_uri == "gs://bucket/file1.pdf"
    assert request_contents.parts[2].file_data is not None
    assert request_contents.parts[2].file_data.mime_type == "text/plain"
    assert request_contents.parts[2].file_data.file_uri == "gs://bucket/file2.txt"


def test_get_structured_analysis_raises_when_retry_not_allowed(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    mock_response = create_mock_response(
        text="invalid json",
        prompt_token_count=5,
        candidates_token_count=5,
    )
    mock_models_api.generate_content.return_value = mock_response

    ai_provider = AiProvider(MockOutputSchema)

    with pytest.raises(ValueError, match="could not be parsed"):
        ai_provider.get_structured_analysis(prompt="prompt", file_uris=[])


def test_get_structured_analysis_retries_without_tools(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    first_response = create_mock_response(
        text="call:google_search.search not json",
        prompt_token_count=11,
        candidates_token_count=4,
        thoughts_token_count=2,
    )
    second_response = create_mock_response(
        text='{"risk_score": 4, "summary": "Fallback success"}',
        prompt_token_count=7,
        candidates_token_count=6,
        thoughts_token_count=1,
    )
    mock_models_api.generate_content.side_effect = [first_response, second_response]

    ai_provider = AiProvider(output_schema=MockOutputSchema)
    ai_provider.logger = MagicMock()

    (
        result,
        total_input_tokens,
        total_output_tokens,
        total_thinking_tokens,
        fallback_input_tokens,
        fallback_output_tokens,
        fallback_thinking_tokens,
    ) = ai_provider.get_structured_analysis(prompt="retry", file_uris=["gs://bucket/file.pdf"])

    assert result.summary == "Fallback success"
    assert total_input_tokens == 11
    assert total_output_tokens == 10
    assert total_thinking_tokens == 3
    assert fallback_input_tokens == 7
    assert fallback_output_tokens == 6
    assert fallback_thinking_tokens == 1
    assert mock_models_api.generate_content.call_count == 2
    assert ai_provider.logger.warning.called

    first_config = mock_models_api.generate_content.call_args_list[0].kwargs["config"]
    second_config = mock_models_api.generate_content.call_args_list[1].kwargs["config"]
    assert first_config.tools
    assert second_config.tools == []


def test_get_structured_analysis_skips_candidate_without_metadata(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    mock_response = create_mock_response(
        text='{"risk_score": 2, "summary": "no metadata"}',
        prompt_token_count=1,
        candidates_token_count=1,
    )
    mock_response.candidates[0].grounding_metadata = None
    mock_models_api.generate_content.return_value = mock_response

    ai_provider = AiProvider(MockOutputSchema)
    ai_provider.logger = MagicMock()

    ai_provider.get_structured_analysis(prompt="prompt", file_uris=[])

    assert not any(
        "Grounding metadata" in str(call.args[0]) for call in ai_provider.logger.info.call_args_list if call.args
    )


def test_get_structured_analysis_logs_grounding_metadata(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    mock_response = create_mock_response(
        text='{"risk_score": 3, "summary": "metadata"}',
        prompt_token_count=2,
        candidates_token_count=2,
    )
    grounding_metadata = MagicMock()
    grounding_metadata.web_search_queries = ["query-data"]
    grounding_metadata.grounded_content = ["ref"]
    mock_response.candidates[0].grounding_metadata = grounding_metadata
    mock_models_api.generate_content.return_value = mock_response

    ai_provider = AiProvider(output_schema=MockOutputSchema)
    ai_provider.logger = MagicMock()

    ai_provider.get_structured_analysis(prompt="prompt", file_uris=[])

    ai_provider.logger.info.assert_any_call(
        "Grounding metadata web_search_queries (candidate %s): %s",
        0,
        ["query-data"],
    )
    ai_provider.logger.info.assert_any_call(
        "Grounding metadata grounded_content (candidate %s): %s",
        0,
        ["ref"],
    )


def test_count_tokens_for_analysis_uses_default_mime_type(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    mock_models_api.count_tokens.return_value = types.CountTokensResponse(total_tokens=50)

    ai_provider = AiProvider(MockOutputSchema)
    input_tokens, _, _ = ai_provider.count_tokens_for_analysis("prompt", ["gs://bucket/file"])

    assert input_tokens == 50
    _, kwargs = mock_models_api.count_tokens.call_args
    parts = kwargs["contents"].parts
    assert parts[1].file_data.mime_type == "application/octet-stream"


def test_generate_content_response_respects_tools_flag(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    mock_models_api, _, _, _ = mock_ai_provider

    ai_provider = AiProvider(MockOutputSchema)
    request_contents = types.Content(role="user", parts=[types.Part(text="test")])

    ai_provider._generate_content_response(request_contents, max_output_tokens=None, enable_tools=True)
    ai_provider._generate_content_response(request_contents, max_output_tokens=None, enable_tools=False)

    first_config = mock_models_api.generate_content.call_args_list[0].kwargs["config"]
    second_config = mock_models_api.generate_content.call_args_list[1].kwargs["config"]
    assert first_config.tools
    assert second_config.tools == []


def test_should_retry_without_tools_detects_tool_call(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)

    part = MagicMock()
    part.text = "call:google_search.search"
    candidate = MagicMock()
    candidate.content.parts = [part]
    response = MagicMock()
    response.candidates = [candidate]

    assert ai_provider._should_retry_without_tools(response) is True


def test_should_retry_without_tools_returns_false_when_missing_parts(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)

    candidate = MagicMock()
    candidate.content = MagicMock()
    candidate.content.parts = [MagicMock(text=None)]
    response = MagicMock()
    response.candidates = [candidate]

    assert ai_provider._should_retry_without_tools(response) is False


def test_should_retry_without_tools_returns_false_when_no_candidates(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)

    response = MagicMock()
    response.candidates = []

    assert ai_provider._should_retry_without_tools(response) is False


def test_should_retry_without_tools_returns_false_when_candidate_content_missing(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)

    candidate = MagicMock()
    candidate.content = None
    response = MagicMock()
    response.candidates = [candidate]

    assert ai_provider._should_retry_without_tools(response) is False


def test_should_retry_without_tools_returns_false_when_parts_missing(
    mock_ai_provider: tuple[MagicMock, MagicMock, MagicMock, MagicMock],
) -> None:
    _, _, _, _ = mock_ai_provider
    ai_provider = AiProvider(MockOutputSchema)

    candidate = MagicMock()
    candidate.content = MagicMock()
    candidate.content.parts = None
    response = MagicMock()
    response.candidates = [candidate]

    assert ai_provider._should_retry_without_tools(response) is False
