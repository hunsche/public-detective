"""This module contains the unit tests for the PricingService."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from public_detective.services.pricing_service import PricingService


@pytest.fixture
def mock_config() -> MagicMock:
    """Provides a mock Config object with predefined cost values."""
    mock = MagicMock()
    mock.GCP_GEMINI_TEXT_INPUT_COST = Decimal("7.750969275")
    mock.GCP_GEMINI_TEXT_INPUT_LONG_COST = Decimal("15.50193855")
    mock.GCP_GEMINI_TEXT_OUTPUT_COST = Decimal("62.0077542")
    mock.GCP_GEMINI_TEXT_OUTPUT_LONG_COST = Decimal("93.0116313")
    mock.GCP_GEMINI_THINKING_OUTPUT_COST = Decimal("62.0077542")
    mock.GCP_GEMINI_THINKING_OUTPUT_LONG_COST = Decimal("93.0116313")
    return mock


@patch("public_detective.services.pricing_service.ConfigProvider.get_config")
def test_calculate_short_context(mock_get_config: MagicMock, mock_config: MagicMock) -> None:
    """Tests cost calculation for a short context."""
    # Arrange
    mock_get_config.return_value = mock_config
    service = PricingService()
    input_tokens = 100_000
    output_tokens = 50_000
    thinking_tokens = 10_000

    # Act
    input_cost, output_cost, thinking_cost, total_cost = service.calculate(input_tokens, output_tokens, thinking_tokens)

    # Assert
    expected_input_cost = (Decimal(input_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_INPUT_COST
    expected_output_cost = (Decimal(output_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_OUTPUT_COST
    expected_thinking_cost = (Decimal(thinking_tokens) / 1_000_000) * mock_config.GCP_GEMINI_THINKING_OUTPUT_COST
    expected_total_cost = expected_input_cost + expected_output_cost + expected_thinking_cost

    assert input_cost == expected_input_cost
    assert output_cost == expected_output_cost
    assert thinking_cost == expected_thinking_cost
    assert total_cost == expected_total_cost


@patch("public_detective.services.pricing_service.ConfigProvider.get_config")
def test_calculate_long_context(mock_get_config: MagicMock, mock_config: MagicMock) -> None:
    """Tests cost calculation for a long context."""
    # Arrange
    mock_get_config.return_value = mock_config
    service = PricingService()
    input_tokens = 300_000  # Exceeds the 200k threshold
    output_tokens = 50_000
    thinking_tokens = 10_000

    # Act
    input_cost, output_cost, thinking_cost, total_cost = service.calculate(input_tokens, output_tokens, thinking_tokens)

    # Assert
    expected_input_cost = (Decimal(input_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_INPUT_LONG_COST
    expected_output_cost = (Decimal(output_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST
    expected_thinking_cost = (Decimal(thinking_tokens) / 1_000_000) * mock_config.GCP_GEMINI_THINKING_OUTPUT_LONG_COST
    expected_total_cost = expected_input_cost + expected_output_cost + expected_thinking_cost

    assert input_cost == expected_input_cost
    assert output_cost == expected_output_cost
    assert thinking_cost == expected_thinking_cost
    assert total_cost == expected_total_cost


@patch("public_detective.services.pricing_service.ConfigProvider.get_config")
def test_calculate_zero_tokens(mock_get_config: MagicMock, mock_config: MagicMock) -> None:
    """Tests cost calculation with zero tokens."""
    # Arrange
    mock_get_config.return_value = mock_config
    service = PricingService()
    input_tokens = 0
    output_tokens = 0
    thinking_tokens = 0

    # Act
    input_cost, output_cost, thinking_cost, total_cost = service.calculate(input_tokens, output_tokens, thinking_tokens)

    # Assert
    assert input_cost == Decimal("0")
    assert output_cost == Decimal("0")
    assert thinking_cost == Decimal("0")
    assert total_cost == Decimal("0")
