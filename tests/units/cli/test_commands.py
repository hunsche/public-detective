from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

from cli.commands import analyze, pre_analyze, retry
from click.testing import CliRunner


# --- Tests for 'retry' command ---
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
    """
    Tests that the retry command works as expected when there are analyses to retry.
    """
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
    mock_service_instance.retry_analyses.assert_called_once_with(
        initial_backoff_hours, max_retries, timeout_hours
    )
    assert f"Successfully triggered {retried_count} analyses for retry." in result.output
    assert result.exit_code == 0


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
    """
    Tests that the retry command works as expected when there are no analyses to retry.
    """
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

    mock_service_instance.retry_analyses.assert_called_once_with(
        initial_backoff_hours, max_retries, timeout_hours
    )
    assert "No analyses found to retry." in result.output
    assert result.exit_code == 0


# --- Tests for 'analyze' command ---
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
    """
    Tests that the analyze command works as expected.
    """
    runner = CliRunner()
    analysis_id = uuid4()

    mock_service_instance = MagicMock()
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(analyze, ["--analysis-id", str(analysis_id)])

    mock_db_manager.get_engine.assert_called_once()
    mock_analysis_service.assert_called_once()
    mock_service_instance.run_specific_analysis.assert_called_once_with(analysis_id)
    assert "Analysis triggered successfully!" in result.output
    assert result.exit_code == 0


def test_analyze_command_missing_id():
    """
    Tests that the analyze command fails if the --analysis-id is missing.
    """
    runner = CliRunner()
    result = runner.invoke(analyze, [], catch_exceptions=False)
    assert "Missing option '--analysis-id'" in result.output
    assert result.exit_code != 0


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
    """
    Tests that the analyze command handles exceptions gracefully.
    """
    runner = CliRunner()
    analysis_id = uuid4()

    mock_service_instance = MagicMock()
    mock_service_instance.run_specific_analysis.side_effect = Exception("Test error")
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(analyze, ["--analysis-id", str(analysis_id)])

    assert "An error occurred: Test error" in result.output
    assert result.exit_code != 0


# --- Tests for 'pre-analyze' command ---
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
    """
    Tests the pre-analysis command with valid dates.
    """
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

    assert "Pre-analysis completed successfully!" in result.output
    assert result.exit_code == 0


def test_pre_analysis_command_with_invalid_date_range():
    """
    Tests that the pre-analysis command fails with an invalid date range.
    """
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

    assert "Start date cannot be after end date." in result.output
    assert result.exit_code != 0


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
    """
    Tests that the pre-analysis command handles exceptions gracefully.
    """
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

    assert "An error occurred: Test error" in result.output
    assert result.exit_code != 0
