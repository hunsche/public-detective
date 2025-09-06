import unittest
from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

from cli.commands import analyze, pre_analyze, retry, trigger_ranked_analysis
from click.testing import CliRunner


class TestRetryCommand(unittest.TestCase):
    @patch("cli.commands.DatabaseManager")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.FileRecordsRepository")
    @patch("cli.commands.ProcurementsRepository")
    @patch("cli.commands.StatusHistoryRepository")
    @patch("cli.commands.BudgetLedgerRepository")
    @patch("cli.commands.AnalysisService")
    def test_retry_command_success(
        self,
        mock_analysis_service,
        mock_budget_ledger_repo,
        mock_status_history_repo,
        mock_procurement_repo,
        mock_file_record_repo,
        mock_analysis_repo,
        mock_ai_provider,
        mock_gcs_provider,
        mock_pubsub_provider,
        mock_db_manager,
    ):
        runner = CliRunner()
        initial_backoff_hours = 6
        max_retries = 3
        timeout_hours = 1
        retried_count = 5

        mock_service_instance = MagicMock()
        mock_service_instance.retry_analyses.return_value = retried_count
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(
            retry,
            [
                "--initial-backoff-hours",
                str(initial_backoff_hours),
                "--max-retries",
                str(max_retries),
                "--timeout-hours",
                str(timeout_hours),
            ],
        )

        mock_db_manager.get_engine.assert_called_once()
        mock_analysis_service.assert_called_once()
        mock_service_instance.retry_analyses.assert_called_once_with(initial_backoff_hours, max_retries, timeout_hours)
        self.assertIn(f"Successfully triggered {retried_count} analyses for retry.", result.output)
        self.assertEqual(result.exit_code, 0)

    @patch("cli.commands.DatabaseManager")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.FileRecordsRepository")
    @patch("cli.commands.ProcurementsRepository")
    @patch("cli.commands.StatusHistoryRepository")
    @patch("cli.commands.BudgetLedgerRepository")
    @patch("cli.commands.AnalysisService")
    def test_retry_command_no_analyses(
        self,
        mock_analysis_service,
        mock_budget_ledger_repo,  # noqa: F841
        mock_status_history_repo,  # noqa: F841
        mock_procurement_repo,  # noqa: F841
        mock_file_record_repo,  # noqa: F841
        mock_analysis_repo,  # noqa: F841
        mock_ai_provider,  # noqa: F841
        mock_gcs_provider,  # noqa: F841
        mock_pubsub_provider,  # noqa: F841
        mock_db_manager,  # noqa: F841
    ):
        runner = CliRunner()
        initial_backoff_hours = 6
        max_retries = 3
        timeout_hours = 1

        mock_service_instance = MagicMock()
        mock_service_instance.retry_analyses.return_value = 0
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(
            retry,
            [
                "--initial-backoff-hours",
                str(initial_backoff_hours),
                "--max-retries",
                str(max_retries),
                "--timeout-hours",
                str(timeout_hours),
            ],
        )

        mock_service_instance.retry_analyses.assert_called_once_with(initial_backoff_hours, max_retries, timeout_hours)
        self.assertIn("No analyses found to retry.", result.output)
        self.assertEqual(result.exit_code, 0)


class TestAnalysisCommand(unittest.TestCase):
    @patch("cli.commands.DatabaseManager")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.FileRecordsRepository")
    @patch("cli.commands.ProcurementsRepository")
    @patch("cli.commands.StatusHistoryRepository")
    @patch("cli.commands.BudgetLedgerRepository")
    @patch("cli.commands.AnalysisService")
    def test_analyze_command_success(
        self,
        mock_analysis_service,
        mock_budget_ledger_repo,  # noqa: F841
        mock_status_history_repo,  # noqa: F841
        mock_procurement_repo,  # noqa: F841
        mock_file_record_repo,  # noqa: F841
        mock_analysis_repo,  # noqa: F841
        mock_ai_provider,  # noqa: F841
        mock_gcs_provider,  # noqa: F841
        mock_pubsub_provider,  # noqa: F841
        mock_db_manager,
    ):
        runner = CliRunner()
        analysis_id = uuid4()

        mock_service_instance = MagicMock()
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(analyze, ["--analysis-id", str(analysis_id)])

        mock_db_manager.get_engine.assert_called_once()
        mock_analysis_service.assert_called_once()
        mock_service_instance.run_specific_analysis.assert_called_once_with(analysis_id)
        self.assertIn("Analysis triggered successfully!", result.output)
        self.assertEqual(result.exit_code, 0)

    def test_analyze_command_missing_id(self):
        runner = CliRunner()
        result = runner.invoke(analyze, [], catch_exceptions=False)
        self.assertIn("Missing option '--analysis-id'", result.output)
        self.assertNotEqual(result.exit_code, 0)

    @patch("cli.commands.DatabaseManager")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.FileRecordsRepository")
    @patch("cli.commands.ProcurementsRepository")
    @patch("cli.commands.StatusHistoryRepository")
    @patch("cli.commands.BudgetLedgerRepository")
    @patch("cli.commands.AnalysisService")
    def test_analyze_command_exception(
        self,
        mock_analysis_service,
        mock_budget_ledger_repo,  # noqa: F841
        mock_status_history_repo,  # noqa: F841
        mock_procurement_repo,  # noqa: F841
        mock_file_record_repo,  # noqa: F841
        mock_analysis_repo,  # noqa: F841
        mock_ai_provider,  # noqa: F841
        mock_gcs_provider,  # noqa: F841
        mock_pubsub_provider,  # noqa: F841
        mock_db_manager,  # noqa: F841
    ):
        runner = CliRunner()
        analysis_id = uuid4()

        mock_service_instance = MagicMock()
        mock_service_instance.run_specific_analysis.side_effect = Exception("Test error")
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(analyze, ["--analysis-id", str(analysis_id)])

        self.assertIn("An error occurred: Test error", result.output)
        self.assertNotEqual(result.exit_code, 0)


class TestTriggerRankedAnalysisCommand(unittest.TestCase):
    @patch("cli.commands.DatabaseManager")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.FileRecordsRepository")
    @patch("cli.commands.ProcurementsRepository")
    @patch("cli.commands.StatusHistoryRepository")
    @patch("cli.commands.BudgetLedgerRepository")
    @patch("cli.commands.AnalysisService")
    def test_trigger_ranked_analysis_command_success(
        self,
        mock_analysis_service,
        mock_budget_ledger_repo,
        mock_status_history_repo,
        mock_procurement_repo,
        mock_file_record_repo,
        mock_analysis_repo,
        mock_ai_provider,
        mock_gcs_provider,
        mock_pubsub_provider,
        mock_db_manager,
    ):
        runner = CliRunner()
        daily_budget = "100.00"
        zero_vote_budget_percentage = "10.0"
        triggered_count = 5

        mock_service_instance = MagicMock()
        mock_service_instance.trigger_ranked_analyses.return_value = triggered_count
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(
            trigger_ranked_analysis,
            [
                "--daily-budget",
                daily_budget,
                "--zero-vote-budget-percentage",
                zero_vote_budget_percentage,
            ],
        )

        self.assertIn(f"Successfully triggered {triggered_count} ranked analyses.", result.output)
        self.assertEqual(result.exit_code, 0)

    @patch("cli.commands.DatabaseManager")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.FileRecordsRepository")
    @patch("cli.commands.ProcurementsRepository")
    @patch("cli.commands.StatusHistoryRepository")
    @patch("cli.commands.BudgetLedgerRepository")
    @patch("cli.commands.AnalysisService")
    def test_trigger_ranked_analysis_command_exception(
        self,
        mock_analysis_service,
        mock_budget_ledger_repo,
        mock_status_history_repo,
        mock_procurement_repo,
        mock_file_record_repo,
        mock_analysis_repo,
        mock_ai_provider,
        mock_gcs_provider,
        mock_pubsub_provider,
        mock_db_manager,
    ):
        runner = CliRunner()
        daily_budget = "100.00"

        mock_service_instance = MagicMock()
        mock_service_instance.trigger_ranked_analyses.side_effect = Exception("Test error")
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(
            trigger_ranked_analysis,
            [
                "--daily-budget",
                daily_budget,
            ],
        )

        self.assertIn("An error occurred: Test error", result.output)
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()


class TestPreAnalysisCommand(unittest.TestCase):
    @patch("cli.commands.DatabaseManager")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.FileRecordsRepository")
    @patch("cli.commands.ProcurementsRepository")
    @patch("cli.commands.StatusHistoryRepository")
    @patch("cli.commands.BudgetLedgerRepository")
    @patch("cli.commands.AnalysisService")
    def test_pre_analysis_command_with_valid_dates(
        self,
        mock_analysis_service,
        mock_budget_ledger_repo,  # noqa: F841
        mock_status_history_repo,  # noqa: F841
        mock_procurement_repo,  # noqa: F841
        mock_file_record_repo,  # noqa: F841
        mock_analysis_repo,  # noqa: F841
        mock_ai_provider,  # noqa: F841
        mock_gcs_provider,  # noqa: F841
        mock_pubsub_provider,  # noqa: F841
        mock_db_manager,  # noqa: F841
    ):
        runner = CliRunner()
        start_date = "2025-01-01"
        end_date = "2025-01-02"
        batch_size = 50
        sleep_seconds = 30

        mock_service_instance = MagicMock()
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(
            pre_analyze,
            [
                "--start-date",
                start_date,
                "--end-date",
                end_date,
                "--batch-size",
                str(batch_size),
                "--sleep-seconds",
                str(sleep_seconds),
            ],
        )

        mock_service_instance.run_pre_analysis.assert_called_once_with(
            date(2025, 1, 1),
            date(2025, 1, 2),
            batch_size,
            sleep_seconds,
            None,  # max_messages
        )

        self.assertIn("Pre-analysis completed successfully!", result.output)
        self.assertEqual(result.exit_code, 0)

    def test_pre_analysis_command_with_invalid_date_range(self):
        runner = CliRunner()
        start_date = "2025-01-02"
        end_date = "2025-01-01"

        result = runner.invoke(
            pre_analyze,
            [
                "--start-date",
                start_date,
                "--end-date",
                end_date,
            ],
            catch_exceptions=False,
        )

        self.assertIn("Start date cannot be after end date.", result.output)
        self.assertNotEqual(result.exit_code, 0)

    @patch("cli.commands.DatabaseManager")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.FileRecordsRepository")
    @patch("cli.commands.ProcurementsRepository")
    @patch("cli.commands.StatusHistoryRepository")
    @patch("cli.commands.BudgetLedgerRepository")
    @patch("cli.commands.AnalysisService")
    def test_pre_analysis_command_exception(
        self,
        mock_analysis_service,
        mock_budget_ledger_repo,  # noqa: F841
        mock_status_history_repo,  # noqa: F841
        mock_procurement_repo,  # noqa: F841
        mock_file_record_repo,  # noqa: F841
        mock_analysis_repo,  # noqa: F841
        mock_ai_provider,  # noqa: F841
        mock_gcs_provider,  # noqa: F841
        mock_pubsub_provider,  # noqa: F841
        mock_db_manager,  # noqa: F841
    ):
        runner = CliRunner()
        start_date = "2025-01-01"
        end_date = "2025-01-01"

        mock_service_instance = MagicMock()
        mock_service_instance.run_pre_analysis.side_effect = Exception("Test error")
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(
            pre_analyze,
            [
                "--start-date",
                start_date,
                "--end-date",
                end_date,
            ],
        )

        self.assertIn("An error occurred: Test error", result.output)
        self.assertNotEqual(result.exit_code, 0)
