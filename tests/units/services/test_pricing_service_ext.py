from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from public_detective.services.pricing_service import Modality, PricingService


@pytest.fixture
def pricing_service():
    """Provides a PricingService instance with a mocked config."""
    with patch("public_detective.services.pricing_service.ConfigProvider") as mock_provider:
        mock_config = MagicMock()
        # Standard context costs
        mock_config.GCP_GEMINI_TEXT_INPUT_COST = Decimal("0.0035")
        mock_config.GCP_GEMINI_AUDIO_INPUT_COST = Decimal("0.002")
        mock_config.GCP_GEMINI_IMAGE_INPUT_COST = Decimal("0.0025")
        mock_config.GCP_GEMINI_VIDEO_INPUT_COST = Decimal("0.004")
        mock_config.GCP_GEMINI_TEXT_OUTPUT_COST = Decimal("0.0015")
        mock_config.GCP_GEMINI_THINKING_OUTPUT_COST = Decimal("0.0005")
        # Long context costs
        mock_config.GCP_GEMINI_TEXT_INPUT_LONG_COST = Decimal("0.007")
        mock_config.GCP_GEMINI_AUDIO_INPUT_LONG_COST = Decimal("0.004")
        mock_config.GCP_GEMINI_IMAGE_INPUT_LONG_COST = Decimal("0.005")
        mock_config.GCP_GEMINI_VIDEO_INPUT_LONG_COST = Decimal("0.008")
        mock_config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST = Decimal("0.003")
        mock_config.GCP_GEMINI_THINKING_OUTPUT_LONG_COST = Decimal("0.001")

        mock_provider.get_config.return_value = mock_config
        service = PricingService()
        yield service


@pytest.mark.parametrize(
    "modality, expected_input_cost_per_million",
    [
        (Modality.TEXT, Decimal("0.0035")),
        (Modality.AUDIO, Decimal("0.002")),
        (Modality.IMAGE, Decimal("0.0025")),
        (Modality.VIDEO, Decimal("0.004")),
    ],
)
def test_calculate_standard_context_modalities(pricing_service, modality, expected_input_cost_per_million):
    """Tests cost calculation for different modalities in a standard context."""
    input_tokens = 100_000
    output_tokens = 10_000
    thinking_tokens = 5_000

    input_cost, output_cost, thinking_cost, total_cost = pricing_service.calculate(
        input_tokens, output_tokens, thinking_tokens, modality
    )

    expected_input = (Decimal(input_tokens) / 1_000_000) * expected_input_cost_per_million
    expected_output = (Decimal(output_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_COST
    expected_thinking = (Decimal(thinking_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_THINKING_OUTPUT_COST

    assert input_cost == expected_input
    assert output_cost == expected_output
    assert thinking_cost == expected_thinking
    assert total_cost == expected_input + expected_output + expected_thinking


@pytest.mark.parametrize(
    "modality, expected_input_cost_per_million",
    [
        (Modality.TEXT, Decimal("0.007")),
        (Modality.AUDIO, Decimal("0.004")),
        (Modality.IMAGE, Decimal("0.005")),
        (Modality.VIDEO, Decimal("0.008")),
    ],
)
def test_calculate_long_context_modalities(pricing_service, modality, expected_input_cost_per_million):
    """Tests cost calculation for different modalities in a long context."""
    input_tokens = 250_000
    output_tokens = 10_000
    thinking_tokens = 5_000

    input_cost, output_cost, thinking_cost, total_cost = pricing_service.calculate(
        input_tokens, output_tokens, thinking_tokens, modality
    )

    expected_input = (Decimal(input_tokens) / 1_000_000) * expected_input_cost_per_million
    expected_output = (Decimal(output_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST
    expected_thinking = (
        Decimal(thinking_tokens) / 1_000_000
    ) * pricing_service.config.GCP_GEMINI_THINKING_OUTPUT_LONG_COST

    assert input_cost == expected_input
    assert output_cost == expected_output
    assert thinking_cost == expected_thinking
    assert total_cost == expected_input + expected_output + expected_thinking
