from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def analysis_service() -> AnalysisService:
    """Creates an AnalysisService instance with mocked dependencies."""
    procurement_repo = MagicMock()
    analysis_repo = MagicMock()
    source_document_repo = MagicMock()
    file_record_repo = MagicMock()
    status_history_repo = MagicMock()
    budget_ledger_repo = MagicMock()
    ai_provider = MagicMock()
    gcs_provider = MagicMock()
    http_provider = MagicMock()
    pubsub_provider = MagicMock()

    service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        http_provider=http_provider,
        pubsub_provider=pubsub_provider,
    )
    service.file_type_provider = MagicMock()
    service.image_converter_provider = MagicMock()
    service.converter_service = MagicMock()
    service.pricing_service = MagicMock()
    service.ranking_service = MagicMock()
    return service


def test_run_ranked_analysis_manual_budget(analysis_service: AnalysisService) -> None:
    """Tests run_ranked_analysis with manual budget."""
    analysis1 = MagicMock(
        analysis_id=uuid4(),
        procurement_control_number="1",
        version_number=1,
        total_cost=Decimal("10.00"),
        votes_count=1,
    )
    analysis2 = MagicMock(
        analysis_id=uuid4(), procurement_control_number="2", version_number=1, total_cost=Decimal("5.00"), votes_count=0
    )

    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1, analysis2]

    procurement1 = MagicMock(spec=Procurement, is_stable=True, current_priority_score=100)
    procurement1.entity_unit = MagicMock(ibge_code="1")
    procurement1.pncp_control_number = "1"

    procurement2 = MagicMock(spec=Procurement, is_stable=True, current_priority_score=50)
    procurement2.entity_unit = MagicMock(ibge_code="2")
    procurement2.pncp_control_number = "2"

    def get_procurement(control_number: str, version: int) -> Procurement | None:
        if control_number == "1":
            return procurement1
        if control_number == "2":
            return procurement2
        return None

    analysis_service.procurement_repo.get_procurement_by_id_and_version.side_effect = get_procurement

    with patch.object(analysis_service, "run_specific_analysis") as mock_run:
        triggered = analysis_service.run_ranked_analysis(
            use_auto_budget=False,
            budget_period=None,
            zero_vote_budget_percent=50,
            budget=Decimal("100.00"),
            max_messages=10,
        )

        assert len(triggered) == 2
        assert mock_run.call_count == 2


def test_run_ranked_analysis_budget_exhausted(analysis_service: AnalysisService) -> None:
    """Tests run_ranked_analysis stops when budget is exhausted."""
    analysis1 = MagicMock(
        analysis_id=uuid4(),
        procurement_control_number="1",
        version_number=1,
        total_cost=Decimal("60.00"),
        votes_count=1,
    )
    analysis2 = MagicMock(
        analysis_id=uuid4(),
        procurement_control_number="2",
        version_number=1,
        total_cost=Decimal("50.00"),
        votes_count=1,
    )

    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1, analysis2]

    procurement1 = MagicMock(spec=Procurement, is_stable=True, current_priority_score=100)
    procurement1.entity_unit = MagicMock(ibge_code="1")

    procurement2 = MagicMock(spec=Procurement, is_stable=True, current_priority_score=90)
    procurement2.entity_unit = MagicMock(ibge_code="2")

    analysis_service.procurement_repo.get_procurement_by_id_and_version.side_effect = [procurement1, procurement2]

    with patch.object(analysis_service, "run_specific_analysis") as mock_run:
        triggered = analysis_service.run_ranked_analysis(
            use_auto_budget=False,
            budget_period=None,
            zero_vote_budget_percent=50,
            budget=Decimal("100.00"),
            max_messages=10,
        )

        assert len(triggered) == 1
        assert triggered[0] == analysis1
        assert mock_run.call_count == 1


def test_run_ranked_analysis_zero_vote_budget(analysis_service: AnalysisService) -> None:
    """Tests run_ranked_analysis respects zero-vote budget."""
    # Budget 100, zero-vote 10% -> 10.00
    # Analysis 1: Cost 5, Votes 0 -> Consumes 5 from zero-vote (remaining 5)
    # Analysis 2: Cost 6, Votes 0 -> Exceeds remaining zero-vote (5) -> Skipped

    analysis1 = MagicMock(
        analysis_id=uuid4(), procurement_control_number="1", version_number=1, total_cost=Decimal("5.00"), votes_count=0
    )
    analysis2 = MagicMock(
        analysis_id=uuid4(), procurement_control_number="2", version_number=1, total_cost=Decimal("6.00"), votes_count=0
    )

    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1, analysis2]

    procurement1 = MagicMock(spec=Procurement, is_stable=True, current_priority_score=100)
    procurement1.entity_unit = MagicMock(ibge_code="1")

    procurement2 = MagicMock(spec=Procurement, is_stable=True, current_priority_score=90)
    procurement2.entity_unit = MagicMock(ibge_code="2")

    analysis_service.procurement_repo.get_procurement_by_id_and_version.side_effect = [procurement1, procurement2]

    with patch.object(analysis_service, "run_specific_analysis") as mock_run:
        triggered = analysis_service.run_ranked_analysis(
            use_auto_budget=False,
            budget_period=None,
            zero_vote_budget_percent=10,
            budget=Decimal("100.00"),
            max_messages=10,
        )

        assert len(triggered) == 1
        assert triggered[0] == analysis1
        assert mock_run.call_count == 1


def test_run_ranked_analysis_unstable_procurement(analysis_service: AnalysisService) -> None:
    """Tests run_ranked_analysis skips unstable procurements."""
    analysis1 = MagicMock(analysis_id=uuid4(), procurement_control_number="1", version_number=1)

    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1]

    procurement1 = MagicMock(spec=Procurement, is_stable=False)
    procurement1.pncp_control_number = "1"

    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = procurement1

    with patch.object(analysis_service, "run_specific_analysis") as mock_run:
        triggered = analysis_service.run_ranked_analysis(
            use_auto_budget=False,
            budget_period=None,
            zero_vote_budget_percent=50,
            budget=Decimal("100.00"),
            max_messages=10,
        )

        assert len(triggered) == 0
        assert mock_run.call_count == 0


def test_run_ranked_analysis_auto_budget(analysis_service: AnalysisService) -> None:
    """Tests run_ranked_analysis with auto budget."""
    with patch.object(analysis_service, "_calculate_auto_budget", return_value=Decimal("50.00")) as mock_calc:
        analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = []

        analysis_service.run_ranked_analysis(
            use_auto_budget=True, budget_period="daily", zero_vote_budget_percent=50, budget=None, max_messages=10
        )

        mock_calc.assert_called_with("daily")


def test_run_ranked_analysis_invalid_args(analysis_service: AnalysisService) -> None:
    """Tests run_ranked_analysis with invalid arguments."""
    with pytest.raises(ValueError, match="Budget period must be provided"):
        analysis_service.run_ranked_analysis(use_auto_budget=True, budget_period=None, zero_vote_budget_percent=50)

    with pytest.raises(ValueError, match="Either a manual budget"):
        analysis_service.run_ranked_analysis(
            use_auto_budget=False, budget_period=None, zero_vote_budget_percent=50, budget=None
        )
