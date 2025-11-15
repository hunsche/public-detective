"""Unit tests for the RankingService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from source.public_detective.models.procurements import Procurement
from source.public_detective.repositories.analyses import AnalysisRepository
from source.public_detective.services.pricing import PricingService
from source.public_detective.services.ranking import RankingService

if TYPE_CHECKING:
    from source.public_detective.services.analysis import AIFileCandidate


@pytest.fixture
def mock_analysis_repo() -> MagicMock:
    """Provides a mock AnalysisRepository."""
    return MagicMock()


@pytest.fixture
def mock_pricing_service() -> MagicMock:
    """Provides a mock PricingService."""
    return MagicMock()


@pytest.fixture
def ranking_service(mock_analysis_repo: AnalysisRepository, mock_pricing_service: PricingService) -> RankingService:
    """Provides a RankingService instance with mocked dependencies."""
    return RankingService(analysis_repo=mock_analysis_repo, pricing_service=mock_pricing_service)


def test_calculate_priority(ranking_service: RankingService) -> None:
    """Tests the calculate_priority method with a basic scenario."""
    procurement = MagicMock(spec=Procurement)
    procurement.total_estimated_value = Decimal("500000")
    procurement.object_description = "serviços de saúde"
    procurement.votes_count = 10
    procurement.last_update_date = datetime.now(timezone.utc) - timedelta(days=3)
    procurement.proposal_closing_date = datetime.now(timezone.utc) + timedelta(days=10)

    candidates: list[AIFileCandidate] = []
    analysis_id = uuid4()

    with (
        patch.object(ranking_service.analysis_repo, "get_analysis_by_id") as mock_get_analysis,
        patch.object(ranking_service.pricing_service, "calculate") as mock_calculate,
    ):
        mock_get_analysis.return_value = MagicMock(input_tokens_used=1000)
        mock_calculate.return_value = (
            Decimal("0.01"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0.01"),
        )

        result = ranking_service.calculate_priority(procurement, candidates, analysis_id)

    assert result.quality_score is not None
    assert result.estimated_cost is not None
    assert result.potential_impact_score is not None
    assert result.priority_score is not None
    assert result.is_stable is not None
    assert result.last_changed_at is not None
    assert result.temporal_score is not None
