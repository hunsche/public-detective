"""This module defines the service for calculating AI analysis costs."""

from decimal import Decimal
from enum import Enum, auto
from typing import cast

from public_detective.providers.config import Config, ConfigProvider


class Modality(Enum):
    """Represents the modality of the analysis."""

    TEXT = auto()
    AUDIO = auto()
    IMAGE = auto()
    VIDEO = auto()


class PricingService:
    """A service to calculate the cost of a generative AI analysis."""

    config: Config

    def __init__(self) -> None:
        """Initializes the PricingService."""
        self.config = ConfigProvider.get_config()

    def _calculate_cost(self, tokens: int, cost_per_million: Decimal) -> Decimal:
        """Calculates the cost for a given number of tokens and a rate per million.

        Args:
            tokens: The number of tokens.
            cost_per_million: The cost for one million tokens.

        Returns:
            The calculated cost.
        """
        if tokens == 0:
            return Decimal("0")
        return (Decimal(tokens) / 1_000_000) * cost_per_million

    def _get_input_cost_per_million(self, modality: Modality, is_long_context: bool) -> Decimal:
        """Determines the input cost per million tokens based on modality and context length.

        Args:
            modality: The modality of the analysis (e.g., TEXT, VIDEO).
            is_long_context: A flag indicating if the context is long.

        Returns:
            The cost per million tokens for the input.
        """
        if is_long_context:
            if modality == Modality.TEXT:
                return cast(Decimal, self.config.GCP_GEMINI_TEXT_INPUT_LONG_COST)
            elif modality == Modality.AUDIO:
                return cast(Decimal, self.config.GCP_GEMINI_AUDIO_INPUT_LONG_COST)
            elif modality == Modality.IMAGE:
                return cast(Decimal, self.config.GCP_GEMINI_IMAGE_INPUT_LONG_COST)
            elif modality == Modality.VIDEO:
                return cast(Decimal, self.config.GCP_GEMINI_VIDEO_INPUT_LONG_COST)
        else:
            if modality == Modality.TEXT:
                return cast(Decimal, self.config.GCP_GEMINI_TEXT_INPUT_COST)
            elif modality == Modality.AUDIO:
                return cast(Decimal, self.config.GCP_GEMINI_AUDIO_INPUT_COST)
            elif modality == Modality.IMAGE:
                return cast(Decimal, self.config.GCP_GEMINI_IMAGE_INPUT_COST)
            elif modality == Modality.VIDEO:
                return cast(Decimal, self.config.GCP_GEMINI_VIDEO_INPUT_COST)

        raise ValueError(f"Unknown modality or context combination: {modality}, {is_long_context}")

    def _get_output_cost_per_million(self, is_long_context: bool) -> Decimal:
        """Determines the output cost per million tokens based on context length.

        Args:
            is_long_context: A flag indicating if the context is long.

        Returns:
            The cost per million tokens for the output.
        """
        if is_long_context:
            return cast(Decimal, self.config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST)
        return cast(Decimal, self.config.GCP_GEMINI_TEXT_OUTPUT_COST)

    def _get_thinking_cost_per_million(self, is_long_context: bool) -> Decimal:
        """Determines the thinking cost per million tokens based on context length.

        Args:
            is_long_context: A flag indicating if the context is long.

        Returns:
            The cost per million tokens for thinking.
        """
        if is_long_context:
            return cast(Decimal, self.config.GCP_GEMINI_TEXT_OUTPUT_LONG_COST)
        return cast(Decimal, self.config.GCP_GEMINI_TEXT_OUTPUT_COST)

    def calculate_total_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int,
        modality: Modality,
        search_queries_count: int = 0,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        """Calculates the cost of an analysis based on token counts and pricing.

        Args:
            input_tokens: The number of input tokens used.
            output_tokens: The number of output tokens used.
            thinking_tokens: The number of thinking tokens used.
            modality: The modality of the analysis.
            search_queries_count: The number of search queries performed.

        Returns:
            A tuple containing the input cost, output cost, thinking cost,
            search cost, and total cost.
        """
        is_long_context = input_tokens > 200_000

        input_cost_per_million = self._get_input_cost_per_million(modality, is_long_context)
        input_cost = self._calculate_cost(input_tokens, input_cost_per_million)

        output_cost_per_million = self._get_output_cost_per_million(is_long_context)
        output_cost = self._calculate_cost(output_tokens, output_cost_per_million)

        thinking_cost_per_million = self._get_thinking_cost_per_million(is_long_context)
        thinking_cost = self._calculate_cost(thinking_tokens, thinking_cost_per_million)

        search_cost = (Decimal(search_queries_count) / 1000) * self.config.GCP_GEMINI_SEARCH_QUERY_COST

        total_cost = input_cost + output_cost + thinking_cost + search_cost

        return input_cost, output_cost, thinking_cost, search_cost, total_cost
