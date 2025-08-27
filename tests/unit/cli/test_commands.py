import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from cli.commands import analysis_command
from click.testing import CliRunner


class TestAnalysisCommand(unittest.TestCase):
    @patch("cli.commands.AnalysisService")
    @patch("cli.commands.ProcurementRepository")
    @patch("cli.commands.FileRecordRepository")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.DatabaseManager")
    def test_analysis_command_with_valid_dates(
        self,
        mock_db_manager,
        mock_pubsub_provider,
        mock_gcs_provider,
        mock_ai_provider,
        mock_analysis_repo,
        mock_file_record_repo,
        mock_procurement_repo,
        mock_analysis_service,
    ):
        runner = CliRunner()
        start_date = "2025-01-01"
        end_date = "2025-01-02"

        # Mock the service instance
        mock_service_instance = MagicMock()
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(analysis_command, ["--start-date", start_date, "--end-date", end_date])

        # Verify that the service was called correctly
        mock_service_instance.run_analysis.assert_called_once_with(
            date(2025, 1, 1),
            date(2025, 1, 2),
        )

        # Verify success message
        self.assertIn("Analysis completed successfully!", result.output)
        self.assertEqual(result.exit_code, 0)

    def test_analysis_command_with_invalid_dates(self):
        runner = CliRunner()
        start_date = "2025-01-02"
        end_date = "2025-01-01"
        result = runner.invoke(analysis_command, ["--start-date", start_date, "--end-date", end_date])
        self.assertIn("Start date cannot be after end date.", result.output)
        self.assertNotEqual(result.exit_code, 0)

    @patch("cli.commands.AnalysisService")
    @patch("cli.commands.ProcurementRepository")
    @patch("cli.commands.FileRecordRepository")
    @patch("cli.commands.AnalysisRepository")
    @patch("cli.commands.AiProvider")
    @patch("cli.commands.GcsProvider")
    @patch("cli.commands.PubSubProvider")
    @patch("cli.commands.DatabaseManager")
    def test_analysis_command_exception(
        self,
        mock_db_manager,
        mock_pubsub_provider,
        mock_gcs_provider,
        mock_ai_provider,
        mock_analysis_repo,
        mock_file_record_repo,
        mock_procurement_repo,
        mock_analysis_service,
    ):
        runner = CliRunner()
        start_date = "2025-01-01"
        end_date = "2025-01-02"

        # Mock the service to raise an exception
        mock_service_instance = MagicMock()
        mock_service_instance.run_analysis.side_effect = Exception("Test error")
        mock_analysis_service.return_value = mock_service_instance

        result = runner.invoke(analysis_command, ["--start-date", start_date, "--end-date", end_date])

        # Verify error message
        self.assertIn("An error occurred: Test error", result.output)
        self.assertEqual(result.exit_code, 0)  # Click commands exit 0 on handled exceptions


if __name__ == "__main__":
    unittest.main()
