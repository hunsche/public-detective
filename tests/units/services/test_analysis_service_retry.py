import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from models.analyses import Analysis, AnalysisResult
from models.procurement_analysis_status import ProcurementAnalysisStatus
from services.analysis import AnalysisService


class TestAnalysisServiceRetry(unittest.TestCase):
    def setUp(self):
        self.mock_procurement_repo = MagicMock()
        self.mock_analysis_repo = MagicMock()
        self.mock_file_record_repo = MagicMock()
        self.mock_status_history_repo = MagicMock()
        self.mock_ai_provider = MagicMock()
        self.mock_gcs_provider = MagicMock()
        self.mock_pubsub_provider = MagicMock()
        self.mock_token_prices_repo = MagicMock()

        self.analysis_service = AnalysisService(
            procurement_repo=self.mock_procurement_repo,
            analysis_repo=self.mock_analysis_repo,
            file_record_repo=self.mock_file_record_repo,
            status_history_repo=self.mock_status_history_repo,
            token_prices_repo=self.mock_token_prices_repo,
            ai_provider=self.mock_ai_provider,
            gcs_provider=self.mock_gcs_provider,
            pubsub_provider=self.mock_pubsub_provider,
        )

    def test_retry_analyses_max_retries_reached(self):
        # Arrange
        analysis = AnalysisResult(
            analysis_id="a4e7e61a-9126-4e4c-8f35-7a4b6306a7f3",
            procurement_control_number="123",
            version_number=1,
            status=ProcurementAnalysisStatus.ANALYSIS_FAILED,
            retry_count=3,
            ai_analysis=Analysis(risk_score=0, risk_score_rationale="", procurement_summary="", analysis_summary=""),
            updated_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        self.mock_analysis_repo.get_analyses_to_retry.return_value = [analysis]

        # Act
        retried_count = self.analysis_service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=1)

        # Assert
        self.assertEqual(retried_count, 0)
        self.mock_analysis_repo.save_retry_analysis.assert_not_called()

    def test_retry_analyses_backoff_period_not_passed(self):
        # Arrange
        analysis = AnalysisResult(
            analysis_id="a4e7e61a-9126-4e4c-8f35-7a4b6306a7f3",
            procurement_control_number="123",
            version_number=1,
            status=ProcurementAnalysisStatus.ANALYSIS_FAILED,
            retry_count=1,
            ai_analysis=Analysis(risk_score=0, risk_score_rationale="", procurement_summary="", analysis_summary=""),
            updated_at=datetime.now(timezone.utc),
        )
        self.mock_analysis_repo.get_analyses_to_retry.return_value = [analysis]

        # Act
        retried_count = self.analysis_service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=1)

        # Assert
        self.assertEqual(retried_count, 0)
        self.mock_analysis_repo.save_retry_analysis.assert_not_called()

    def test_retry_analyses_success(self):
        # Arrange
        analysis = AnalysisResult(
            analysis_id="a4e7e61a-9126-4e4c-8f35-7a4b6306a7f3",
            procurement_control_number="123",
            version_number=1,
            status=ProcurementAnalysisStatus.ANALYSIS_FAILED,
            retry_count=1,
            ai_analysis=Analysis(risk_score=0, risk_score_rationale="", procurement_summary="", analysis_summary=""),
            updated_at=datetime.now(timezone.utc) - timedelta(days=1),
            document_hash="hash",
            input_tokens_used=10,
            output_tokens_used=20,
        )
        self.mock_analysis_repo.get_analyses_to_retry.return_value = [analysis]
        new_analysis_id = "b5e8e72b-9126-4e4c-8f35-7a4b6306a7f4"
        self.mock_analysis_repo.save_retry_analysis.return_value = new_analysis_id

        # Act
        with patch.object(self.analysis_service, "run_specific_analysis") as mock_run_specific_analysis:
            retried_count = self.analysis_service.retry_analyses(
                initial_backoff_hours=1, max_retries=3, timeout_hours=1
            )

            # Assert
            self.assertEqual(retried_count, 1)
            self.mock_analysis_repo.save_retry_analysis.assert_called_once_with(
                procurement_control_number="123",
                version_number=1,
                document_hash="hash",
                input_tokens_used=10,
                output_tokens_used=20,
                retry_count=2,
            )
            mock_run_specific_analysis.assert_called_once_with(new_analysis_id)
