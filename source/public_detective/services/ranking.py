"""This module defines the RankingService, responsible for scoring and
prioritizing procurements.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from source.public_detective.models.file_records import ExclusionReason
from source.public_detective.models.procurements import Procurement
from source.public_detective.repositories.analyses import AnalysisRepository
from source.public_detective.services.pricing import Modality, PricingService

if TYPE_CHECKING:
    from source.public_detective.services.analysis import AIFileCandidate


class RankingService:
    """A service for ranking and prioritizing procurements."""

    analysis_repo: AnalysisRepository
    pricing_service: PricingService

    # These weights can be tuned based on business priorities.
    W_IMPACTO = 1.5
    W_QUALIDADE = 1.0
    W_CUSTO = 0.1
    W_VOTOS = 0.2

    # Quarantine period to determine if a procurement is stable.
    STABILITY_PERIOD_HOURS = 48

    HIGH_IMPACT_KEYWORDS = [
        "saúde",
        "hospitalar",
        "educação",
        "saneamento",
        "infraestrutura",
    ]

    def __init__(
        self,
        analysis_repo: AnalysisRepository,
        pricing_service: PricingService,
    ) -> None:
        """Initializes the service with its dependencies."""
        self.analysis_repo = analysis_repo
        self.pricing_service = pricing_service

    def calculate_priority(
        self,
        procurement: Procurement,
        candidates: list[AIFileCandidate],
        analysis_id: UUID | None,
    ) -> Procurement:
        """Calculates and updates the procurement with all ranking scores."""
        quality_score = self._calculate_quality_score(candidates)
        estimated_cost = self._calculate_estimated_cost(analysis_id)
        potential_impact_score = self._calculate_potential_impact_score(procurement)
        is_stable = self._is_stable(procurement)

        # Calculate adjusted impact based on votes
        vote_count = procurement.votes_count or 0
        impacto_ajustado = potential_impact_score * (1 + self.W_VOTOS * vote_count)

        # Calculate the final priority score
        priority_score = (
            (self.W_IMPACTO * impacto_ajustado)
            + (self.W_QUALIDADE * quality_score)
            - (self.W_CUSTO * float(estimated_cost))
        )

        # Update the procurement object
        procurement.quality_score = quality_score
        procurement.estimated_cost = estimated_cost
        procurement.potential_impact_score = potential_impact_score
        procurement.priority_score = int(priority_score)
        procurement.is_stable = is_stable
        procurement.last_changed_at = procurement.last_update_date

        return procurement

    def _calculate_quality_score(self, candidates: list[AIFileCandidate]) -> int:
        """Calculated the quality score based on file information."""
        if not candidates:
            return 0

        score = 100
        # Penalties for different file quality issues.
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

        # Penalize for a low ratio of usable files.
        total_files = len(candidates)
        bad_files = sum(1 for c in candidates if c.exclusion_reason)
        usable_ratio = (
            (total_files - bad_files) / total_files if total_files > 0 else 0
        )

        if usable_ratio < 0.5:
            score -= 20
        elif usable_ratio < 0.8:
            score -= 10

        return max(0, score)

    def _calculate_estimated_cost(self, analysis_id: UUID | None) -> Decimal:
        """Calculates the estimated cost of analysis."""
        if not analysis_id:
            return Decimal("0.0")
        analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
        if not analysis or not analysis.input_tokens_used:
            return Decimal("0.0")

        _, _, _, total_cost = self.pricing_service.calculate(
            analysis.input_tokens_used, 0, 0, modality=Modality.TEXT
        )
        return total_cost

    def _calculate_potential_impact_score(self, procurement: Procurement) -> int:
        """Calculates the potential impact score based on metadata."""
        score = 0

        # Score based on estimated value
        if procurement.total_estimated_value:
            if procurement.total_estimated_value > 1_000_000:
                score += 50
            elif procurement.total_estimated_value > 100_000:
                score += 25

        # Score based on keywords
        for keyword in self.HIGH_IMPACT_KEYWORDS:
            if keyword in procurement.object_description.lower():
                score += 20

        return min(score, 100)  # Cap the score at 100

    def _is_stable(self, procurement: Procurement) -> bool:
        """Determines if the procurement is stable."""
        now = datetime.now(timezone.utc)
        last_updated = procurement.last_update_date.astimezone(timezone.utc)
        quarantine_period = timedelta(hours=self.STABILITY_PERIOD_HOURS)
        return now - last_updated > quarantine_period
