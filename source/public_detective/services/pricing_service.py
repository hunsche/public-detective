"""This module defines the service for calculating AI analysis costs."""

from decimal import Decimal

from public_detective.providers.config import Config, ConfigProvider


class PricingService:
    """A service to calculate the cost of a generative AI analysis."""

    config: Config

    def __init__(self) -> None:
        """Initializes the PricingService."""
        self.config = ConfigProvider.get_config()

    def calculate(
        self,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """Calculates the cost of an analysis based on token counts and pricing.

        Args:
            input_tokens: The number of input tokens used.
            output_tokens: The number of output tokens used.
            thinking_tokens: The number of thinking tokens used.

        Returns:
            A tuple containing the input cost, output cost, thinking cost, and
            total cost.
        """
        is_long_context = input_tokens > 200_000

        # Determine input cost
        if is_long_context:
            input_cost_per_million = self.config.GCP_GEMINI_TEXT_INPUT_LONG_COST
        else:
            input_cost_per_million = self.config.GCP_GEMINI_TEXT_INPUT_COST

        input_cost = (Decimal(input_tokens) / 1_000_000) * input_cost_per_million

        # Determine output cost
        if is_long_context:
            output_cost_per_million = self.config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST
        else:
            output_cost_per_million = self.config.GCP_GEMINI_TEXT_OUTPUT_COST

        output_cost = (Decimal(output_tokens) / 1_000_000) * output_cost_per_million

        # Determine thinking cost
        if is_long_context:
            thinking_cost_per_million = self.config.GCP_GEMINI_THINKING_OUTPUT_LONG_COST
        else:
            thinking_cost_per_million = self.config.GCP_GEMINI_THINKING_OUTPUT_COST

        thinking_cost = (Decimal(thinking_tokens) / 1_000_000) * thinking_cost_per_million

        total_cost = input_cost + output_cost + thinking_cost

        return input_cost, output_cost, thinking_cost, total_cost
