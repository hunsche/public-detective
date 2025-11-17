"""Unit tests for the RankingService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.models.procurements import Procurement
from public_detective.providers.config import ConfigProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.services.analysis import AIFileCandidate
from public_detective.services.pricing import PricingService
from public_detective.services.ranking import RankingService


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
    config = ConfigProvider.get_config()
    return RankingService(analysis_repo=mock_analysis_repo, pricing_service=mock_pricing_service, config=config)


def test_calculate_priority(ranking_service: RankingService) -> None:
    """Tests the calculate_priority method with a basic scenario."""
    procurement = MagicMock(spec=Procurement)
    procurement.total_estimated_value = Decimal("500000")
    procurement.object_description = "serviços de saúde"
    procurement.votes_count = 10
    procurement.last_update_date = datetime.now(timezone.utc) - timedelta(days=3)
    procurement.proposal_closing_date = datetime.now(timezone.utc) + timedelta(days=10)
    procurement.government_entity = MagicMock(sphere="M")

    candidates: list[AIFileCandidate] = []
    analysis_id = uuid4()

    with (
        patch.object(ranking_service.analysis_repo, "get_analysis_by_id") as mock_get_analysis,
        patch.object(ranking_service.pricing_service, "calculate_total_cost") as mock_calculate_total_cost,
    ):
        mock_get_analysis.return_value = MagicMock(input_tokens_used=1000)
        mock_calculate_total_cost.return_value = (
            Decimal("0.01"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0.01"),
            Decimal("0"),  # Add fallback_cost
        )

        result = ranking_service.calculate_priority(procurement, candidates, analysis_id)
    assert result.quality_score is not None
    assert result.estimated_cost is not None
    assert result.potential_impact_score is not None
    assert result.priority_score is not None
    assert result.is_stable is not None
    assert result.last_changed_at is not None
    assert result.temporal_score is not None
    assert result.federal_bonus_score is not None


def test_calculate_temporal_score(ranking_service: RankingService) -> None:
    """Tests the _calculate_temporal_score method."""
    procurement = MagicMock(spec=Procurement)
    ranking_service.config.RANKING_TEMPORAL_WINDOW_MIN_DAYS = 5
    ranking_service.config.RANKING_TEMPORAL_WINDOW_MAX_DAYS = 15

    # Test case 1: Ideal window
    procurement.proposal_closing_date = datetime.now(timezone.utc) + timedelta(days=10)
    assert ranking_service._calculate_temporal_score(procurement) == 30

    # Test case 2: Close window
    procurement.proposal_closing_date = datetime.now(timezone.utc) + timedelta(days=3)
    assert ranking_service._calculate_temporal_score(procurement) == 15

    # Test case 3: Outside window
    procurement.proposal_closing_date = datetime.now(timezone.utc) + timedelta(days=20)
    assert ranking_service._calculate_temporal_score(procurement) == 0
    procurement.proposal_closing_date = datetime.now(timezone.utc) - timedelta(days=1)
    assert ranking_service._calculate_temporal_score(procurement) == 0

    # Test case 4: No closing date
    procurement.proposal_closing_date = None
    assert ranking_service._calculate_temporal_score(procurement) == 0


def test_calculate_federal_bonus_score(ranking_service: RankingService) -> None:
    """Tests the _calculate_federal_bonus_score method."""
    procurement = MagicMock(spec=Procurement)

    # Test case 1: Federal entity
    procurement.government_entity = MagicMock(sphere="F")
    assert ranking_service._calculate_federal_bonus_score(procurement) == 20

    # Test case 2: Non-federal entity
    procurement.government_entity = MagicMock(sphere="E")
    assert ranking_service._calculate_federal_bonus_score(procurement) == 0
    procurement.government_entity = MagicMock(sphere="M")
    assert ranking_service._calculate_federal_bonus_score(procurement) == 0
