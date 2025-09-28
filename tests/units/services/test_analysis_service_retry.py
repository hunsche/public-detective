from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import Analysis, AnalysisResult
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def analysis_service_fixture() -> dict:
    """
    Sets up the AnalysisService with mock dependencies for testing retry logic.
    """
    mock_procurement_repo = MagicMock()
    mock_analysis_repo = MagicMock(spec=AnalysisRepository)
    mock_source_document_repo = MagicMock()
    mock_file_record_repo = MagicMock()
    mock_status_history_repo = MagicMock()
    mock_ai_provider = MagicMock()
    mock_gcs_provider = MagicMock()
    mock_pubsub_provider = MagicMock()
    mock_budget_ledger_repo = MagicMock()

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
    return {
        "service": service,
        "analysis_repo": mock_analysis_repo,
        "pubsub_provider": mock_pubsub_provider,
    }


def test_retry_analyses_no_analyses_found(analysis_service_fixture: dict) -> None:
    """
    Tests that retry_analyses returns 0 when no analyses are found to retry.
    """
    analysis_repo = analysis_service_fixture["analysis_repo"]
    service = analysis_service_fixture["service"]

    analysis_repo.get_analyses_to_retry.return_value = []
    result = service.retry_analyses(6, 3, 1)

    assert result == 0
    analysis_repo.get_analyses_to_retry.assert_called_once_with(3, 1)


def test_retry_analyses_triggers_eligible_analysis(analysis_service_fixture: dict) -> None:
    """
    Tests that retry_analyses correctly triggers an eligible analysis.
    """
    analysis_repo = analysis_service_fixture["analysis_repo"]
    service = analysis_service_fixture["service"]

    analysis_id = uuid4()
    now = datetime.now(timezone.utc)
    mock_ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
    )
    eligible_analysis = AnalysisResult(
        analysis_id=analysis_id,
        procurement_control_number="123",
        version_number=1,
        status="ANALYSIS_FAILED",
        retry_count=0,
        updated_at=now - timedelta(hours=7),
        document_hash="hash123",
        input_tokens_used=100,
        output_tokens_used=50,
        thinking_tokens_used=10,
        analysis_prompt="Test prompt",
        ai_analysis=mock_ai_analysis,
    )
    analysis_repo.get_analyses_to_retry.return_value = [eligible_analysis]
    analysis_repo.save_retry_analysis.return_value = uuid4()

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        result = service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=1)

        assert result == 1
        analysis_repo.get_analyses_to_retry.assert_called_once_with(3, 1)
        analysis_repo.save_retry_analysis.assert_called_once()
        call_kwargs = analysis_repo.save_retry_analysis.call_args[1]
        assert call_kwargs["procurement_control_number"] == "123"
        assert call_kwargs["retry_count"] == 1
        assert call_kwargs["thinking_tokens_used"] == 10
        mock_run_specific.assert_called_once()


def test_retry_analyses_skips_ineligible_analysis_due_to_backoff(analysis_service_fixture: dict) -> None:
    """
    Tests that retry_analyses skips an analysis that is within the backoff period.
    """
    analysis_repo = analysis_service_fixture["analysis_repo"]
    service = analysis_service_fixture["service"]

    analysis_id = uuid4()
    now = datetime.now(timezone.utc)
    mock_ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
    )
    ineligible_analysis = AnalysisResult(
        analysis_id=analysis_id,
        procurement_control_number="123",
        version_number=1,
        status="ANALYSIS_FAILED",
        retry_count=0,
        updated_at=now - timedelta(hours=1),  # Backoff is 6 hours
        document_hash="hash123",
        input_tokens_used=100,
        output_tokens_used=50,
        analysis_prompt="Test prompt",
        ai_analysis=mock_ai_analysis,
    )
    analysis_repo.get_analyses_to_retry.return_value = [ineligible_analysis]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        result = service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=1)

        assert result == 0
        analysis_repo.get_analyses_to_retry.assert_called_once_with(3, 1)
        analysis_repo.save_retry_analysis.assert_not_called()
        mock_run_specific.assert_not_called()


def test_retry_analyses_run_specific_fails(analysis_service_fixture: dict) -> None:
    """
    Tests that retry_analyses handles exceptions from run_specific_analysis.
    """
    analysis_repo = analysis_service_fixture["analysis_repo"]
    service = analysis_service_fixture["service"]

    analysis_id = uuid4()
    now = datetime.now(timezone.utc)
    eligible_analysis = MagicMock(
        analysis_id=analysis_id,
        procurement_control_number="123",
        version_number=1,
        document_hash="hash123",
        input_tokens_used=100,
        output_tokens_used=50,
        retry_count=0,
        updated_at=now - timedelta(hours=7),
    )
    analysis_repo.get_analyses_to_retry.return_value = [eligible_analysis]
    analysis_repo.save_retry_analysis.return_value = uuid4()

    with patch.object(service, "run_specific_analysis", side_effect=Exception("test error")):
        with pytest.raises(AnalysisError):
            service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=1)


def test_retry_analyses_too_soon(analysis_service_fixture: dict) -> None:
    """
    Tests that retry_analyses skips an analysis if the backoff period has not passed.
    """
    analysis_repo = analysis_service_fixture["analysis_repo"]
    service = analysis_service_fixture["service"]

    analysis_id = uuid4()
    now = datetime.now(timezone.utc)
    eligible_analysis = AnalysisResult(
        analysis_id=analysis_id,
        procurement_control_number="123",
        version_number=1,
        status="ANALYSIS_FAILED",
        retry_count=1,
        updated_at=now - timedelta(hours=1),  # backoff is 6 * 2 = 12 hours
        analysis_prompt="Test prompt",
        ai_analysis=Analysis(
            risk_score=5,
            risk_score_rationale="Rationale",
            procurement_summary="Summary",
            analysis_summary="Summary",
            red_flags=[],
        ),
    )
    analysis_repo.get_analyses_to_retry.return_value = [eligible_analysis]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=1)
        mock_run_specific.assert_not_called()
