"""This module defines the RankingService.

It is responsible for scoring and prioritizing procurements.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from source.public_detective.models.procurements import Procurement
from source.public_detective.providers.logging import LoggingProvider
from source.public_detective.repositories.analyses import AnalysisRepository
from source.public_detective.services.pricing import Modality, PricingService
from source.public_detective.services.ranking_config import ranking_config

if TYPE_CHECKING:
    from source.public_detective.services.analysis import AIFileCandidate


class RankingService:
    """A service for ranking and prioritizing procurements."""

    analysis_repo: AnalysisRepository
    pricing_service: PricingService

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
        self.logger = LoggingProvider().get_logger()

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
        temporal_score = self._calculate_temporal_score(procurement)

        vote_count = procurement.votes_count or 0
        vote_factor = math.log(vote_count + 1, 10)
        impacto_ajustado = potential_impact_score * (1 + ranking_config.W_VOTES * vote_factor)

        priority_score = (
            (ranking_config.W_IMPACT * impacto_ajustado)
            + (ranking_config.W_QUALITY * quality_score)
            + (ranking_config.W_TEMPORAL * temporal_score)
            - (ranking_config.W_COST * float(estimated_cost))
        )

        procurement.quality_score = quality_score
        procurement.estimated_cost = estimated_cost
        procurement.potential_impact_score = potential_impact_score
        procurement.priority_score = int(priority_score)
        procurement.is_stable = is_stable
        procurement.last_changed_at = procurement.last_update_date

        self.logger.info(
            "Procurement ranking calculated.",
            extra={
                "procurement_id": procurement.id,
                "quality_score": quality_score,
                "estimated_cost": estimated_cost,
                "potential_impact_score": potential_impact_score,
                "temporal_score": temporal_score,
                "is_stable": is_stable,
                "vote_count": vote_count,
                "vote_factor": vote_factor,
                "adjusted_impact": impacto_ajustado,
                "final_priority_score": priority_score,
            },
        )

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
        penalty_points = ranking_config.QUALITY_PENALTY_POINTS

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
            if procurement.total_estimated_value > ranking_config.IMPACT_VALUE_THRESHOLDS["HIGH"]:
                score += ranking_config.IMPACT_VALUE_SCORES["HIGH"]
            elif procurement.total_estimated_value > ranking_config.IMPACT_VALUE_THRESHOLDS["MEDIUM"]:
                score += ranking_config.IMPACT_VALUE_SCORES["MEDIUM"]

        for keyword in ranking_config.HIGH_IMPACT_KEYWORDS:
            if keyword in procurement.object_description.lower():
                score += ranking_config.IMPACT_KEYWORD_SCORE

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
        quarantine_period = timedelta(hours=ranking_config.STABILITY_PERIOD_HOURS)
        return now - last_updated > quarantine_period

    def _calculate_temporal_score(self, procurement: Procurement) -> int:
        """Calculates a score based on the proximity to the deadline.

        Args:
            procurement: The procurement to check.

        Returns:
            An integer score from 0 to 100.
        """
        if not ranking_config.TEMPORAL_SCORE_ENABLED or not procurement.deadline_date:
            return 0

        now = datetime.now(timezone.utc)
        deadline = procurement.deadline_date.astimezone(timezone.utc)
        days_to_deadline = (deadline - now).days

        min_days = ranking_config.TEMPORAL_WINDOW_DAYS_MIN
        max_days = ranking_config.TEMPORAL_WINDOW_DAYS_MAX

        if min_days <= days_to_deadline <= max_days:
            return 100
        elif days_to_deadline < min_days:
            return int(max(0, 100 - (min_days - days_to_deadline) * 10))
        else:
            return int(max(0, 100 - (days_to_deadline - max_days) * 5))
