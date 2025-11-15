"""This module defines the RankingService.

It is responsible for scoring and prioritizing procurements.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from source.public_detective.models.file_records import ExclusionReason
from source.public_detective.models.procurements import Procurement
from source.public_detective.providers.config import Config, ConfigProvider
from source.public_detective.repositories.analyses import AnalysisRepository
from source.public_detective.services.pricing import Modality, PricingService

if TYPE_CHECKING:
    from source.public_detective.services.analysis import AIFileCandidate


class RankingService:
    """A service for ranking and prioritizing procurements."""

    analysis_repo: AnalysisRepository
    pricing_service: PricingService
    config: Config

    def __init__(
        self,
        analysis_repo: AnalysisRepository,
        pricing_service: PricingService,
    ) -> None:
        """Initializes the service with its dependencies.

        Args:
            analysis_repo: The repository for analysis data.
            pricing_service: The service for calculating costs.
        """
        self.analysis_repo = analysis_repo
        self.pricing_service = pricing_service
        self.config = ConfigProvider.get_config()

    def calculate_priority(
        self,
        procurement: Procurement,
        candidates: list[AIFileCandidate],
        analysis_id: UUID | None,
    ) -> Procurement:
        """Calculates and updates the procurement with all ranking scores.

        Args:
            procurement: The procurement to be scored.
            candidates: A list of file candidates for quality scoring.
            analysis_id: The ID of the analysis for cost estimation.

        Returns:
            The updated procurement object with all scores.
        """
        quality_score = self._calculate_quality_score(candidates)
        estimated_cost = self._calculate_estimated_cost(analysis_id)
        potential_impact_score = self._calculate_potential_impact_score(procurement)
        is_stable = self._is_stable(procurement)

        vote_count = procurement.votes_count or 0
        if vote_count > 0:
            vote_factor = 1 + self.config.RANKING_W_VOTOS * math.log(vote_count + 1)
        else:
            vote_factor = 1

        impacto_ajustado = potential_impact_score * vote_factor

        priority_score = (
            (self.config.RANKING_W_IMPACTO * impacto_ajustado)
            + (self.config.RANKING_W_QUALIDADE * quality_score)
            - (self.config.RANKING_W_CUSTO * float(estimated_cost))
        )

        procurement.quality_score = quality_score
        procurement.estimated_cost = estimated_cost
        procurement.potential_impact_score = potential_impact_score
        procurement.priority_score = int(priority_score)
        procurement.is_stable = is_stable
        procurement.last_changed_at = procurement.last_update_date
        procurement.temporal_score = self._calculate_temporal_score(procurement)

        return procurement

    def _calculate_temporal_score(self, procurement: Procurement) -> int:
        """Calculates the temporal score based on the proposal closing date.

        Args:
            procurement: The procurement to be scored.

        Returns:
            An integer score from 0 to 100.
        """
        if not procurement.proposal_closing_date:
            return 0

        now = datetime.now(timezone.utc)
        days_until_closing = (procurement.proposal_closing_date - now).days

        min_days = self.config.RANKING_TEMPORAL_WINDOW_MIN_DAYS
        max_days = self.config.RANKING_TEMPORAL_WINDOW_MAX_DAYS

        if min_days <= days_until_closing <= max_days:
            return 100
        elif days_until_closing < min_days:
            return 50
        else:
            return 10

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

    def _calculate_estimated_cost(self, analysis_id: UUID | None) -> Decimal:
        """Calculates the estimated cost of analysis.

        Args:
            analysis_id: The ID of the pre-analysis record.

        Returns:
            The estimated cost as a Decimal.
        """
        if not analysis_id:
            return Decimal("0.0")
        analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
        if not analysis or not analysis.input_tokens_used:
            return Decimal("0.0")

        _, _, _, total_cost = self.pricing_service.calculate(analysis.input_tokens_used, 0, 0, modality=Modality.TEXT)
        return total_cost

    def _calculate_potential_impact_score(self, procurement: Procurement) -> int:
        """Calculates the potential impact score based on metadata.

        Args:
            procurement: The procurement to be scored.

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
        return now - last_updated > quarantine_period
