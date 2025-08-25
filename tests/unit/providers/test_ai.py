from unittest.mock import MagicMock, patch

import pytest
from models.analysis import Analysis
from providers.ai import AiProvider
from pydantic import BaseModel


class MockOutputSchema(BaseModel):
    risk_score: int
    summary: str


@patch("providers.config.ConfigProvider")
@patch("google.generativeai.GenerativeModel")
@patch("google.generativeai.configure")
def test_get_structured_analysis_uses_valid_schema(mock_configure, mock_gen_model, mock_config_provider):  # noqa: F841
    """
    Should generate content with a response schema compatible with the Gemini API,
    ensuring Pydantic validation fields like 'ge' and 'le' are not present.
    """
    # Arrange
    mock_config = MagicMock()
    mock_config.GCP_GEMINI_API_KEY = "fake-api-key"
    mock_config.GCP_GEMINI_MODEL = "gemini-test"
    mock_config_provider.get_config.return_value = mock_config

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
