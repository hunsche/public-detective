import unittest
from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

from click.testing import CliRunner

from source.cli.commands import analyze, pre_analyze, reap_stale_tasks


class TestReapStaleTasksCommand(unittest.TestCase):
    @patch("source.cli.commands.DatabaseManager")
    @patch("source.cli.commands.PubSubProvider")
    @patch("source.cli.commands.GcsProvider")
    @patch("source.cli.commands.AiProvider")
    @patch("source.cli.commands.AnalysisRepository")
    @patch("source.cli.commands.FileRecordsRepository")
    @patch("source.cli.commands.ProcurementsRepository")
    @patch("source.cli.commands.StatusHistoryRepository")
    @patch("source.cli.commands.AnalysisService")
    def test_reap_stale_tasks_command_success(
        self,
        mock_analysis_service,
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
        timeout = 30
        reaped_count = 5

        mock_service_instance = MagicMock()
        mock_service_instance.reap_stale_analyses.return_value = reaped_count
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(reap_stale_tasks, ["--timeout-minutes", str(timeout)])

        mock_db_manager.get_engine.assert_called_once()
        mock_analysis_service.assert_called_once()
        mock_service_instance.reap_stale_analyses.assert_called_once_with(timeout)
        self.assertIn(f"Successfully reset {reaped_count} stale tasks to TIMEOUT status.", result.output)
        self.assertEqual(result.exit_code, 0)

    @patch("source.cli.commands.DatabaseManager")
    @patch("source.cli.commands.PubSubProvider")
    @patch("source.cli.commands.GcsProvider")
    @patch("source.cli.commands.AiProvider")
    @patch("source.cli.commands.AnalysisRepository")
    @patch("source.cli.commands.FileRecordsRepository")
    @patch("source.cli.commands.ProcurementsRepository")
    @patch("source.cli.commands.StatusHistoryRepository")
    @patch("source.cli.commands.AnalysisService")
    def test_reap_stale_tasks_command_no_tasks(
        self,
        mock_analysis_service,
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
        timeout = 15  # default

        mock_service_instance = MagicMock()
        mock_service_instance.reap_stale_analyses.return_value = 0
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(reap_stale_tasks)

        mock_service_instance.reap_stale_analyses.assert_called_once_with(timeout)
        self.assertIn("No stale tasks found.", result.output)
        self.assertEqual(result.exit_code, 0)


class TestAnalysisCommand(unittest.TestCase):
    @patch("source.cli.commands.DatabaseManager")
    @patch("source.cli.commands.PubSubProvider")
    @patch("source.cli.commands.GcsProvider")
    @patch("source.cli.commands.AiProvider")
    @patch("source.cli.commands.AnalysisRepository")
    @patch("source.cli.commands.FileRecordsRepository")
    @patch("source.cli.commands.ProcurementsRepository")
    @patch("source.cli.commands.StatusHistoryRepository")
    @patch("source.cli.commands.AnalysisService")
    def test_analyze_command_success(
        self,
        mock_analysis_service,
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

    @patch("source.cli.commands.DatabaseManager")
    @patch("source.cli.commands.PubSubProvider")
    @patch("source.cli.commands.GcsProvider")
    @patch("source.cli.commands.AiProvider")
    @patch("source.cli.commands.AnalysisRepository")
    @patch("source.cli.commands.FileRecordsRepository")
    @patch("source.cli.commands.ProcurementsRepository")
    @patch("source.cli.commands.StatusHistoryRepository")
    @patch("source.cli.commands.AnalysisService")
    def test_analyze_command_exception(
        self,
        mock_analysis_service,
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


if __name__ == "__main__":
    unittest.main()


class TestPreAnalysisCommand(unittest.TestCase):
    @patch("source.cli.commands.DatabaseManager")
    @patch("source.cli.commands.PubSubProvider")
    @patch("source.cli.commands.GcsProvider")
    @patch("source.cli.commands.AiProvider")
    @patch("source.cli.commands.AnalysisRepository")
    @patch("source.cli.commands.FileRecordsRepository")
    @patch("source.cli.commands.ProcurementsRepository")
    @patch("source.cli.commands.StatusHistoryRepository")
    @patch("source.cli.commands.AnalysisService")
    def test_pre_analysis_command_with_valid_dates(
        self,
        mock_analysis_service,
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

    @patch("source.cli.commands.DatabaseManager")
    @patch("source.cli.commands.PubSubProvider")
    @patch("source.cli.commands.GcsProvider")
    @patch("source.cli.commands.AiProvider")
    @patch("source.cli.commands.AnalysisRepository")
    @patch("source.cli.commands.FileRecordsRepository")
    @patch("source.cli.commands.ProcurementsRepository")
    @patch("source.cli.commands.StatusHistoryRepository")
    @patch("source.cli.commands.AnalysisService")
    def test_pre_analysis_command_exception(
        self,
        mock_analysis_service,
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
