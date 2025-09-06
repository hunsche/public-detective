import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from models.analyses import Analysis, AnalysisResult
from repositories.analyses import AnalysisRepository
from services.analysis import AnalysisService


class TestRetryAnalyses(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_procurement_repo = MagicMock()
        self.mock_analysis_repo = MagicMock(spec=AnalysisRepository)
        self.mock_file_record_repo = MagicMock()
        self.mock_status_history_repo = MagicMock()
        self.mock_ai_provider = MagicMock()
        self.mock_gcs_provider = MagicMock()
        self.mock_pubsub_provider = MagicMock()
        self.mock_budget_ledger_repo = MagicMock()

        self.analysis_service = AnalysisService(
            procurement_repo=self.mock_procurement_repo,
            analysis_repo=self.mock_analysis_repo,
            file_record_repo=self.mock_file_record_repo,
            status_history_repo=self.mock_status_history_repo,
            budget_ledger_repo=self.mock_budget_ledger_repo,
            ai_provider=self.mock_ai_provider,
            gcs_provider=self.mock_gcs_provider,
            pubsub_provider=self.mock_pubsub_provider,
        )

    def test_retry_analyses_no_analyses_found(self) -> None:
        self.mock_analysis_repo.get_analyses_to_retry.return_value = []
        result = self.analysis_service.retry_analyses(6, 3, 1)
        self.assertEqual(result, 0)
        self.mock_analysis_repo.get_analyses_to_retry.assert_called_once_with(3, 1)

    def test_retry_analyses_triggers_eligible_analysis(self) -> None:
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
            ai_analysis=mock_ai_analysis,
        )
        self.mock_analysis_repo.get_analyses_to_retry.return_value = [eligible_analysis]
        self.mock_analysis_repo.save_retry_analysis.return_value = uuid4()

        with patch.object(self.analysis_service, "run_specific_analysis") as mock_run_specific:
            result = self.analysis_service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=1)

            self.assertEqual(result, 1)
            self.mock_analysis_repo.get_analyses_to_retry.assert_called_once_with(3, 1)
            self.mock_analysis_repo.save_retry_analysis.assert_called_once_with(
                procurement_control_number="123",
                version_number=1,
                document_hash="hash123",
                input_tokens_used=100,
                output_tokens_used=50,
                retry_count=1,
            )
            mock_run_specific.assert_called_once()

    def test_retry_analyses_skips_ineligible_analysis_due_to_backoff(self) -> None:
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
            ai_analysis=mock_ai_analysis,
        )
        self.mock_analysis_repo.get_analyses_to_retry.return_value = [ineligible_analysis]

        with patch.object(self.analysis_service, "run_specific_analysis") as mock_run_specific:
            result = self.analysis_service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=1)

            self.assertEqual(result, 0)
            self.mock_analysis_repo.get_analyses_to_retry.assert_called_once_with(3, 1)
            self.mock_analysis_repo.save_retry_analysis.assert_not_called()
            mock_run_specific.assert_not_called()
