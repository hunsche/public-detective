"""Unit tests for the RankingService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.models.file_records import ExclusionReason
from public_detective.models.procurements import Procurement
from public_detective.providers.config import ConfigProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.services.analysis import AIFileCandidate
from public_detective.services.pricing import Modality, PricingService
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
            Decimal("0"),
            Decimal("0.17"),
        )
        ranking_service._calculate_quality_score = MagicMock(return_value=100)

        ranking_service.calculate_priority(procurement, candidates, analysis_id)

        mock_calculate_total_cost.assert_called_with(
            1000,
            ranking_service.config.GCP_GEMINI_MAX_OUTPUT_TOKENS,
            0,
            modality=Modality.TEXT,
            search_queries_count=10,
        )
    assert procurement.current_quality_score == 100
    assert procurement.current_estimated_cost == Decimal("0.17")
    assert procurement.current_potential_impact_score == 55
    assert procurement.current_priority_score == 330
    assert procurement.is_stable is True
    assert procurement.last_changed_at is not None
    assert procurement.temporal_score == 30
    assert procurement.federal_bonus_score == 0


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


def test_calculate_quality_score(ranking_service: RankingService) -> None:
    """Tests the _calculate_quality_score method."""
    # Test case 1: No candidates
    assert ranking_service._calculate_quality_score([]) == 0

    # Test case 2: Perfect candidates
    c1 = MagicMock(spec=AIFileCandidate, exclusion_reason=None)
    c2 = MagicMock(spec=AIFileCandidate, exclusion_reason=None)
    assert ranking_service._calculate_quality_score([c1, c2]) == 100

    # Test case 3: Mixed candidates
    c3 = MagicMock(spec=AIFileCandidate, exclusion_reason=ExclusionReason.EXTRACTION_FAILED)  # -20
    c4 = MagicMock(spec=AIFileCandidate, exclusion_reason=ExclusionReason.CONVERSION_FAILED)  # -15
    # Total score: 100 - 20 - 15 = 65
    # Usable ratio: 2/4 = 0.5 -> Penalty -10 (< 0.8)
    assert ranking_service._calculate_quality_score([c1, c2, c3, c4]) == 55

    # Test case 4: Low usable ratio
    # 1 good, 3 bad. Ratio = 0.25 (< 0.5) -> -20 penalty
    c5 = MagicMock(spec=AIFileCandidate, exclusion_reason=ExclusionReason.UNSUPPORTED_EXTENSION)  # -10
    # Score: 100 - 20 - 15 - 10 = 55. Penalty -20 = 35.
    assert ranking_service._calculate_quality_score([c1, c3, c4, c5]) == 35

    # Test case 5: Very low usable ratio (< 0.8 but >= 0.5)
    # 3 good, 1 bad. Ratio = 0.75. Penalty -10.
    # Bad file: EXTRACTION_FAILED (-20).
    # Score: 100 - 20 = 80. Penalty -10 = 70.
    assert ranking_service._calculate_quality_score([c1, c1, c1, c3]) == 70


def test_calculate_estimated_cost(ranking_service: RankingService) -> None:
    """Tests the _calculate_estimated_cost method."""
    # Test case 1: Input tokens provided
    with patch.object(ranking_service.pricing_service, "calculate_total_cost") as mock_calc:
        mock_calc.return_value = (0, 0, 0, 0, Decimal("0.50"))
        cost = ranking_service._calculate_estimated_cost(None, input_tokens=100)
        assert cost == Decimal("0.50")

    # Test case 2: Analysis ID provided, analysis found
    analysis_id = uuid4()
    with (
        patch.object(ranking_service.analysis_repo, "get_analysis_by_id") as mock_get,
        patch.object(ranking_service.pricing_service, "calculate_total_cost") as mock_calc,
    ):
        mock_get.return_value = MagicMock(input_tokens_used=200)
        mock_calc.return_value = (0, 0, 0, 0, Decimal("1.00"))
        cost = ranking_service._calculate_estimated_cost(analysis_id)
        assert cost == Decimal("1.00")

    # Test case 3: Analysis ID provided, analysis not found
    with patch.object(ranking_service.analysis_repo, "get_analysis_by_id") as mock_get:
        mock_get.return_value = None
        assert ranking_service._calculate_estimated_cost(analysis_id) == Decimal("0.0")

    # Test case 4: No inputs
    assert ranking_service._calculate_estimated_cost(None) == Decimal("0.0")


def test_calculate_potential_impact_score(ranking_service: RankingService) -> None:
    """Tests the _calculate_potential_impact_score method."""
    procurement = MagicMock(spec=Procurement)
    ranking_service.config.RANKING_HIGH_IMPACT_KEYWORDS = ["saude", "educacao"]

    # Test case 1: High value (> 1M), keyword match, bonuses
    procurement.total_estimated_value = Decimal("2000000")
    procurement.object_description = "serviços de saude"
    # Score: 50 (value) + 20 (keyword) + 10 (temporal/3) + 20 (federal) = 100
    assert ranking_service._calculate_potential_impact_score(procurement, 30, 20) == 100

    # Test case 2: Medium value (> 100k), no keyword
    procurement.total_estimated_value = Decimal("500000")
    procurement.object_description = "obras"
    # Score: 25 (value) + 0 (keyword) + 0 (temporal) + 0 (federal) = 25
    assert ranking_service._calculate_potential_impact_score(procurement, 0, 0) == 25

    # Test case 3: Low value, keyword match
    procurement.total_estimated_value = Decimal("50000")
    procurement.object_description = "material de educacao"
    # Score: 0 (value) + 20 (keyword) + 0 + 0 = 20
    assert ranking_service._calculate_potential_impact_score(procurement, 0, 0) == 20


def test_is_stable(ranking_service: RankingService) -> None:
    """Tests the _is_stable method."""
    procurement = MagicMock(spec=Procurement)
    ranking_service.config.RANKING_STABILITY_PERIOD_HOURS = 24

    # Test case 1: Stable (updated > 24h ago)
    procurement.last_update_date = datetime.now(timezone.utc) - timedelta(hours=25)
    assert ranking_service._is_stable(procurement) is True

    # Test case 2: Unstable (updated < 24h ago)
    procurement.last_update_date = datetime.now(timezone.utc) - timedelta(hours=23)
    assert ranking_service._is_stable(procurement) is False
