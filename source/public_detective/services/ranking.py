"""This module defines the RankingService.

It is responsible for scoring and prioritizing procurements.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import numpy as np
from public_detective.models.candidates import AIFileCandidate
from public_detective.models.file_records import ExclusionReason
from public_detective.models.procurements import Procurement
from public_detective.providers.config import Config
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.services.pricing import Modality, PricingService


class RankingService:
    """A service for ranking and prioritizing procurements."""

    analysis_repo: AnalysisRepository
    pricing_service: PricingService
    config: Config

    def __init__(
        self,
        analysis_repo: AnalysisRepository,
        pricing_service: PricingService,
        config: Config,
    ) -> None:
        """Initializes the service with its dependencies.

        Args:
            analysis_repo: The repository for analysis data.
            pricing_service: The service for calculating costs.
            config: The application configuration object.
        """
        self.analysis_repo = analysis_repo
        self.pricing_service = pricing_service
        self.config = config

    def calculate_priority(
        self,
        procurement: Procurement,
        candidates: list[AIFileCandidate],
        analysis_id: UUID | None,
        input_tokens: int | None = None,
    ) -> Procurement:
        """Calculates and updates the procurement with all ranking scores.

        Args:
            procurement: The procurement to be scored.
            candidates: A list of file candidates for quality scoring.
            analysis_id: The ID of the analysis for cost estimation.
            input_tokens: The number of input tokens, if already calculated.

        Returns:
            The updated procurement object with all scores.
        """
        quality_score = self._calculate_quality_score(candidates)
        estimated_cost = self._calculate_estimated_cost(analysis_id, input_tokens)
        temporal_score = self._calculate_temporal_score(procurement)
        federal_bonus_score = self._calculate_federal_bonus_score(procurement)
        potential_impact_score = self._calculate_potential_impact_score(
            procurement, temporal_score, federal_bonus_score
        )
        is_stable = self._is_stable(procurement)

        vote_count = procurement.votes_count or 0
        vote_factor = np.log1p(vote_count)
        adjusted_impact = potential_impact_score * (1 + self.config.RANKING_WEIGHT_VOTES * vote_factor)

        priority_score = (
            (self.config.RANKING_WEIGHT_IMPACT * adjusted_impact)
            + (self.config.RANKING_WEIGHT_QUALITY * quality_score)
            - (self.config.RANKING_WEIGHT_COST * float(estimated_cost))
        )

        procurement.quality_score = quality_score
        procurement.estimated_cost = estimated_cost
        procurement.potential_impact_score = potential_impact_score
        procurement.priority_score = int(priority_score)
        procurement.is_stable = is_stable
        procurement.last_changed_at = procurement.last_update_date
        procurement.temporal_score = temporal_score
        procurement.federal_bonus_score = federal_bonus_score

        return procurement

    def _calculate_quality_score(self, candidates: list[AIFileCandidate]) -> int:
        """Calculates the quality score based on file information.

        Args:
            candidates: A list of AI file candidates.

        Returns:
            An integer score from 0 to 100.
        """
        if not candidates:
            return 0

        score = 100
        penalty_points = {
            ExclusionReason.EXTRACTION_FAILED: 20,
            ExclusionReason.CONVERSION_FAILED: 15,
            ExclusionReason.UNSUPPORTED_EXTENSION: 10,
            ExclusionReason.LOCK_FILE: 5,
            ExclusionReason.TOKEN_LIMIT_EXCEEDED: 5,
        }

        for candidate in candidates:
            if candidate.exclusion_reason:
                score -= penalty_points.get(candidate.exclusion_reason, 0)

        total_files = len(candidates)
        bad_files = sum(1 for c in candidates if c.exclusion_reason)
        usable_ratio = (total_files - bad_files) / total_files if total_files > 0 else 0

        if usable_ratio < 0.5:
            score -= 20
        elif usable_ratio < 0.8:
            score -= 10

        return max(0, score)

    def _calculate_estimated_cost(self, analysis_id: UUID | None, input_tokens: int | None = None) -> Decimal:
        """Calculates the estimated cost of analysis.

        Args:
            analysis_id: The ID of the pre-analysis record.
            input_tokens: The number of input tokens, if already calculated.

        Returns:
            The estimated cost as a Decimal.
        """
        tokens_to_use = input_tokens
        if tokens_to_use is None:
            if not analysis_id:
                return Decimal("0.0")
            analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
            if not analysis or not analysis.input_tokens_used:
                return Decimal("0.0")
            tokens_to_use = analysis.input_tokens_used

        if tokens_to_use is None:
            return Decimal("0.0")

        _, _, _, total_cost_decimal, _ = self.pricing_service.calculate_total_cost(
            tokens_to_use,
            0,
            0,
            modality=Modality.TEXT,
            fallback_input_tokens=0,
            fallback_output_tokens=0,
            fallback_thinking_tokens=0,
        )
        return Decimal(total_cost_decimal)

    def _calculate_potential_impact_score(
        self, procurement: Procurement, temporal_score: int, federal_bonus_score: int
    ) -> int:
        """Calculates the potential impact score based on metadata.

        Args:
            procurement: The procurement to be scored.
            temporal_score: The pre-calculated temporal score.
            federal_bonus_score: The pre-calculated federal bonus score.

        Returns:
            An integer score from 0 to 100.
        """
        score = 0

        if procurement.total_estimated_value:
            if procurement.total_estimated_value > 1_000_000:
                score += 50
            elif procurement.total_estimated_value > 100_000:
                score += 25

        for keyword in self.config.RANKING_HIGH_IMPACT_KEYWORDS:
            if keyword in procurement.object_description.lower():
                score += 20

        score += temporal_score // 3
        score += federal_bonus_score

        return min(score, 100)

    def _is_stable(self, procurement: Procurement) -> bool:
        """Determines if the procurement is stable based on its last update.

        Args:
            procurement: The procurement to check.

        Returns:
            True if the procurement is considered stable, False otherwise.
        """
        now = datetime.now(timezone.utc)
        last_updated = procurement.last_update_date.astimezone(timezone.utc)
        quarantine_period = timedelta(hours=self.config.RANKING_STABILITY_PERIOD_HOURS)
        return bool(now - last_updated > quarantine_period)

    def _calculate_temporal_score(self, procurement: Procurement) -> int:
        """Calculates the temporal score based on the proposal closing date.

        Args:
            procurement: The procurement to check.

        Returns:
            An integer score from 0 to 30.
        """
        if not procurement.proposal_closing_date:
            return 0

        now = datetime.now(timezone.utc)
        time_to_closing = procurement.proposal_closing_date.astimezone(timezone.utc) - now

        if (
            timedelta(days=self.config.RANKING_TEMPORAL_WINDOW_MIN_DAYS)
            <= time_to_closing
            < timedelta(days=self.config.RANKING_TEMPORAL_WINDOW_MAX_DAYS)
        ):
            return 30
        if timedelta(days=0) <= time_to_closing < timedelta(days=self.config.RANKING_TEMPORAL_WINDOW_MIN_DAYS):
            return 15
        return 0

    def _calculate_federal_bonus_score(self, procurement: Procurement) -> int:
        """Calculates a bonus score for federal-level procurements.

        Args:
            procurement: The procurement to check.

        Returns:
            An integer score of 20 for federal procurements, otherwise 0.
        """
        return 20 if procurement.government_entity.sphere == "F" else 0
