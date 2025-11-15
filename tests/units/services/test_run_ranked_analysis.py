"""Unit tests for the run_ranked_analysis method in AnalysisService."""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from source.public_detective.models.procurements import Procurement
from source.public_detective.services.analysis import AnalysisService


@pytest.fixture
def mock_procurement_repo() -> MagicMock:
    """Provides a mock ProcurementsRepository."""
    return MagicMock()


@pytest.fixture
def mock_analysis_repo() -> MagicMock:
    """Provides a mock AnalysisRepository."""
    return MagicMock()


@pytest.fixture
def mock_source_document_repo() -> MagicMock:
    """Provides a mock SourceDocumentsRepository."""
    return MagicMock()


@pytest.fixture
def mock_file_record_repo() -> MagicMock:
    """Provides a mock FileRecordsRepository."""
    return MagicMock()


@pytest.fixture
def mock_status_history_repo() -> MagicMock:
    """Provides a mock StatusHistoryRepository."""
    return MagicMock()


@pytest.fixture
def mock_budget_ledger_repo() -> MagicMock:
    """Provides a mock BudgetLedgerRepository."""
    return MagicMock()


@pytest.fixture
def mock_ai_provider() -> MagicMock:
    """Provides a mock AiProvider."""
    return MagicMock()


@pytest.fixture
def mock_gcs_provider() -> MagicMock:
    """Provides a mock GcsProvider."""
    return MagicMock()


@pytest.fixture
def mock_pubsub_provider() -> MagicMock:
    """Provides a mock PubSubProvider."""
    return MagicMock()


@pytest.fixture
def analysis_service(
    mock_procurement_repo: MagicMock,
    mock_analysis_repo: MagicMock,
    mock_source_document_repo: MagicMock,
    mock_file_record_repo: MagicMock,
    mock_status_history_repo: MagicMock,
    mock_budget_ledger_repo: MagicMock,
    mock_ai_provider: MagicMock,
    mock_gcs_provider: MagicMock,
    mock_pubsub_provider: MagicMock,
) -> AnalysisService:
    """Provides an AnalysisService instance with mocked dependencies."""
    service = AnalysisService(
        procurement_repo=mock_procurement_repo,
        analysis_repo=mock_analysis_repo,
        source_document_repo=mock_source_document_repo,
        file_record_repo=mock_file_record_repo,
        status_history_repo=mock_status_history_repo,
        budget_ledger_repo=mock_budget_ledger_repo,
        ai_provider=mock_ai_provider,
        gcs_provider=mock_gcs_provider,
        pubsub_provider=mock_pubsub_provider,
    )
    service.pricing_service = MagicMock()
    return service


def test_run_ranked_analysis_proportional_allocation(analysis_service: AnalysisService) -> None:
    """Tests the proportional allocation logic for regional diversity."""
    mock_analysis1_cityA = MagicMock(
        analysis_id=uuid.uuid4(),
        procurement_control_number="PCN1",
        version_number=1,
        total_cost=Decimal("10"),
    )
    mock_analysis2_cityA = MagicMock(
        analysis_id=uuid.uuid4(),
        procurement_control_number="PCN2",
        version_number=1,
        total_cost=Decimal("10"),
    )
    mock_analysis1_cityB = MagicMock(
        analysis_id=uuid.uuid4(),
        procurement_control_number="PCN3",
        version_number=1,
        total_cost=Decimal("10"),
    )
    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [
        mock_analysis1_cityA,
        mock_analysis2_cityA,
        mock_analysis1_cityB,
    ]

    mock_proc1 = MagicMock(
        spec=Procurement,
        is_stable=True,
        temporal_score=30,
        priority_score=100,
        entity_unit=MagicMock(ibge_code="A"),
    )
    mock_proc1.pncp_control_number = "PCN1"
    mock_proc2 = MagicMock(
        spec=Procurement,
        is_stable=True,
        temporal_score=30,
        priority_score=90,
        entity_unit=MagicMock(ibge_code="A"),
    )
    mock_proc2.pncp_control_number = "PCN2"
    mock_proc3 = MagicMock(
        spec=Procurement,
        is_stable=True,
        temporal_score=30,
        priority_score=95,
        entity_unit=MagicMock(ibge_code="B"),
    )
    mock_proc3.pncp_control_number = "PCN3"

    def get_procurement_side_effect(control_number: str, _: int) -> MagicMock | None:
        if control_number == "PCN1":
            return mock_proc1
        if control_number == "PCN2":
            return mock_proc2
        if control_number == "PCN3":
            return mock_proc3
        return None

    analysis_service.procurement_repo.get_procurement_by_id_and_version.side_effect = get_procurement_side_effect
    analysis_service.run_specific_analysis = MagicMock()

    triggered_analyses = analysis_service.run_ranked_analysis(
        use_auto_budget=False,
        budget=Decimal("100"),
        budget_period=None,
        zero_vote_budget_percent=10,
        max_messages=2,
    )

    assert len(triggered_analyses) == 2
    assert {a.analysis_id for a in triggered_analyses} == {
        mock_analysis1_cityA.analysis_id,
        mock_analysis1_cityB.analysis_id,
    }
