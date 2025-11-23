"""This module contains the unit tests for the PricingService."""

from collections.abc import Generator
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from public_detective.services.pricing import Modality, PricingService


@pytest.fixture
def pricing_service() -> Generator[PricingService, Any, None]:
    """Provides a PricingService instance with a mocked config."""
    with patch("public_detective.services.pricing.ConfigProvider") as mock_provider:
        mock_config = MagicMock()
        # Standard context costs
        mock_config.GCP_GEMINI_TEXT_INPUT_COST = Decimal("0.0035")
        mock_config.GCP_GEMINI_AUDIO_INPUT_COST = Decimal("0.002")
        mock_config.GCP_GEMINI_IMAGE_INPUT_COST = Decimal("0.0025")
        mock_config.GCP_GEMINI_VIDEO_INPUT_COST = Decimal("0.004")
        mock_config.GCP_GEMINI_TEXT_OUTPUT_COST = Decimal("0.0015")

        # Long context costs
        mock_config.GCP_GEMINI_TEXT_INPUT_LONG_COST = Decimal("0.007")
        mock_config.GCP_GEMINI_AUDIO_INPUT_LONG_COST = Decimal("0.004")
        mock_config.GCP_GEMINI_IMAGE_INPUT_LONG_COST = Decimal("0.005")
        mock_config.GCP_GEMINI_VIDEO_INPUT_LONG_COST = Decimal("0.008")
        mock_config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST = Decimal("0.003")

        mock_config.GCP_GEMINI_LONG_CONTEXT_THRESHOLD = 128000
        mock_config.GCP_GEMINI_SEARCH_QUERY_COST = Decimal("14.00")

        mock_provider.get_config.return_value = mock_config
        service = PricingService()
        yield service


def test_calculate_zero_tokens(pricing_service: PricingService) -> None:
    """Tests cost calculation with zero tokens."""
    (
        input_cost,
        output_cost,
        thinking_cost,
        search_cost,
        total_cost,
    ) = pricing_service.calculate_total_cost(0, 0, 0, Modality.TEXT)
    assert input_cost == Decimal("0")
    assert output_cost == Decimal("0")
    assert thinking_cost == Decimal("0")
    assert search_cost == Decimal("0")
    assert total_cost == Decimal("0")


@pytest.mark.parametrize(
    "modality, expected_input_cost_per_million",
    [
        (Modality.TEXT, Decimal("0.0035")),
        (Modality.AUDIO, Decimal("0.002")),
        (Modality.IMAGE, Decimal("0.0025")),
        (Modality.VIDEO, Decimal("0.004")),
    ],
)
def test_calculate_standard_context_modalities(
    pricing_service: PricingService, modality: Modality, expected_input_cost_per_million: Decimal
) -> None:
    """Tests cost calculation for different modalities in a standard context."""
    input_tokens = 100_000
    output_tokens = 10_000
    thinking_tokens = 5_000

    (
        input_cost,
        output_cost,
        thinking_cost,
        search_cost,
        total_cost,
    ) = pricing_service.calculate_total_cost(input_tokens, output_tokens, thinking_tokens, modality)

    expected_input = (Decimal(input_tokens) / 1_000_000) * expected_input_cost_per_million
    expected_output = (Decimal(output_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_COST
    expected_thinking = (Decimal(thinking_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_COST

    assert input_cost == expected_input
    assert output_cost == expected_output
    assert thinking_cost == expected_thinking
    assert search_cost == Decimal("0")
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
def test_calculate_long_context_modalities(
    pricing_service: PricingService, modality: Modality, expected_input_cost_per_million: Decimal
) -> None:
    """Tests cost calculation for different modalities in a long context."""
    input_tokens = 250_000
    output_tokens = 10_000
    thinking_tokens = 5_000

    (
        input_cost,
        output_cost,
        thinking_cost,
        search_cost,
        total_cost,
    ) = pricing_service.calculate_total_cost(input_tokens, output_tokens, thinking_tokens, modality)

    expected_input = (Decimal(input_tokens) / 1_000_000) * expected_input_cost_per_million
    expected_output = (Decimal(output_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST
    expected_thinking = (Decimal(thinking_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST

    assert input_cost == expected_input
    assert output_cost == expected_output
    assert thinking_cost == expected_thinking
    assert search_cost == Decimal("0")
    assert total_cost == expected_input + expected_output + expected_thinking


def test_calculate_search_cost_zero_queries(pricing_service: PricingService) -> None:
    """Tests cost calculation with zero search queries."""
    input_tokens = 100_000
    output_tokens = 10_000
    thinking_tokens = 5_000
    search_queries = 0

    (
        input_cost,
        output_cost,
        thinking_cost,
        search_cost,
        total_cost,
    ) = pricing_service.calculate_total_cost(
        input_tokens, output_tokens, thinking_tokens, Modality.TEXT, search_queries_count=search_queries
    )

    expected_input = (Decimal(input_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_INPUT_COST
    expected_output = (Decimal(output_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_COST
    expected_thinking = (Decimal(thinking_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_COST
    expected_search = Decimal("0")

    assert input_cost == expected_input
    assert output_cost == expected_output
    assert thinking_cost == expected_thinking
    assert search_cost == expected_search
    assert total_cost == expected_input + expected_output + expected_thinking + expected_search


def test_calculate_search_cost(pricing_service: PricingService) -> None:
    """Tests cost calculation with search queries."""
    input_tokens = 100_000
    output_tokens = 10_000
    thinking_tokens = 5_000
    search_queries = 10

    (
        input_cost,
        output_cost,
        thinking_cost,
        search_cost,
        total_cost,
    ) = pricing_service.calculate_total_cost(
        input_tokens, output_tokens, thinking_tokens, Modality.TEXT, search_queries_count=search_queries
    )

    expected_input = (Decimal(input_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_INPUT_COST
    expected_output = (Decimal(output_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_COST
    expected_thinking = (Decimal(thinking_tokens) / 1_000_000) * pricing_service.config.GCP_GEMINI_TEXT_OUTPUT_COST
    expected_search = (Decimal(search_queries) / 1000) * pricing_service.config.GCP_GEMINI_SEARCH_QUERY_COST

    assert input_cost == expected_input
    assert output_cost == expected_output
    assert thinking_cost == expected_thinking
    assert search_cost == expected_search
    assert total_cost == expected_input + expected_output + expected_thinking + expected_search
