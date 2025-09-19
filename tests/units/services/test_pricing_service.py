"""This module contains the unit tests for the CostCalculator service."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from public_detective.services.pricing_service import PricingService


@pytest.fixture
def mock_config() -> MagicMock:
    """Provides a mock Config object with predefined cost values."""
    mock = MagicMock()
    mock.GCP_GEMINI_TEXT_INPUT_COST = Decimal("10.0")
    mock.GCP_GEMINI_TEXT_INPUT_LONG_COST = Decimal("20.0")
    mock.GCP_GEMINI_TEXT_OUTPUT_COST = Decimal("30.0")
    mock.GCP_GEMINI_TEXT_OUTPUT_LONG_COST = Decimal("40.0")
    mock.GCP_GEMINI_THINKING_OUTPUT_COST = Decimal("50.0")
    mock.GCP_GEMINI_THINKING_OUTPUT_LONG_COST = Decimal("60.0")
    return mock


@patch("public_detective.providers.config.ConfigProvider.get_config")
def test_calculate_short_context_no_thinking(mock_get_config: MagicMock, mock_config: MagicMock) -> None:
    """Tests cost calculation for a short context without thinking mode."""
    mock_get_config.return_value = mock_config
    calculator = PricingService()

    input_tokens = 100_000
    output_tokens = 50_000
    is_thinking_mode = False

    input_cost, output_cost, total_cost = calculator.calculate(input_tokens, output_tokens, is_thinking_mode)

    expected_input_cost = (Decimal(input_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_INPUT_COST
    expected_output_cost = (Decimal(output_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_OUTPUT_COST
    expected_total_cost = expected_input_cost + expected_output_cost

    assert input_cost == expected_input_cost
    assert output_cost == expected_output_cost
    assert total_cost == expected_total_cost


@patch("public_detective.providers.config.ConfigProvider.get_config")
def test_calculate_long_context_no_thinking(mock_get_config: MagicMock, mock_config: MagicMock) -> None:
    """Tests cost calculation for a long context without thinking mode."""
    mock_get_config.return_value = mock_config
    calculator = PricingService()

    input_tokens = 300_000
    output_tokens = 50_000
    is_thinking_mode = False

    input_cost, output_cost, total_cost = calculator.calculate(input_tokens, output_tokens, is_thinking_mode)

    expected_input_cost = (Decimal(input_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_INPUT_LONG_COST
    expected_output_cost = (Decimal(output_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST
    expected_total_cost = expected_input_cost + expected_output_cost

    assert input_cost == expected_input_cost
    assert output_cost == expected_output_cost
    assert total_cost == expected_total_cost


@patch("public_detective.providers.config.ConfigProvider.get_config")
def test_calculate_short_context_with_thinking(mock_get_config: MagicMock, mock_config: MagicMock) -> None:
    """Tests cost calculation for a short context with thinking mode."""
    mock_get_config.return_value = mock_config
    calculator = PricingService()

    input_tokens = 100_000
    output_tokens = 50_000
    is_thinking_mode = True

    input_cost, output_cost, total_cost = calculator.calculate(input_tokens, output_tokens, is_thinking_mode)

    expected_input_cost = (Decimal(input_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_INPUT_COST
    expected_output_cost = (Decimal(output_tokens) / 1_000_000) * mock_config.GCP_GEMINI_THINKING_OUTPUT_COST
    expected_total_cost = expected_input_cost + expected_output_cost

    assert input_cost == expected_input_cost
    assert output_cost == expected_output_cost
    assert total_cost == expected_total_cost


@patch("public_detective.providers.config.ConfigProvider.get_config")
def test_calculate_long_context_with_thinking(mock_get_config: MagicMock, mock_config: MagicMock) -> None:
    """Tests cost calculation for a long context with thinking mode."""
    mock_get_config.return_value = mock_config
    calculator = PricingService()

    input_tokens = 300_000
    output_tokens = 50_000
    is_thinking_mode = True

    input_cost, output_cost, total_cost = calculator.calculate(input_tokens, output_tokens, is_thinking_mode)

    expected_input_cost = (Decimal(input_tokens) / 1_000_000) * mock_config.GCP_GEMINI_TEXT_INPUT_LONG_COST
    expected_output_cost = (Decimal(output_tokens) / 1_000_000) * mock_config.GCP_GEMINI_THINKING_OUTPUT_LONG_COST
    expected_total_cost = expected_input_cost + expected_output_cost

    assert input_cost == expected_input_cost
    assert output_cost == expected_output_cost
    assert total_cost == expected_total_cost


@patch("public_detective.providers.config.ConfigProvider.get_config")
def test_calculate_zero_tokens(mock_get_config: MagicMock, mock_config: MagicMock) -> None:
    """Tests cost calculation with zero tokens."""
    mock_get_config.return_value = mock_config
    calculator = PricingService()

    input_tokens = 0
    output_tokens = 0
    is_thinking_mode = False

    input_cost, output_cost, total_cost = calculator.calculate(input_tokens, output_tokens, is_thinking_mode)

    assert input_cost == Decimal("0")
    assert output_cost == Decimal("0")
    assert total_cost == Decimal("0")
