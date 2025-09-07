from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

from cli.commands import analyze, pre_analyze, retry, trigger_ranked_analysis
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
    mock_analysis_service: MagicMock,
    mock_budget_ledger_repo: MagicMock,
    mock_status_history_repo: MagicMock,
    mock_procurement_repo: MagicMock,
    mock_file_record_repo: MagicMock,
    mock_analysis_repo: MagicMock,
    mock_ai_provider: MagicMock,
    mock_gcs_provider: MagicMock,
    mock_pubsub_provider: MagicMock,
    mock_db_manager: MagicMock,
) -> None:
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
    mock_service_instance.retry_analyses.assert_called_once_with(initial_backoff_hours, max_retries, timeout_hours)
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
    mock_analysis_service: MagicMock,
    mock_budget_ledger_repo: MagicMock,  # noqa: F841
    mock_status_history_repo: MagicMock,  # noqa: F841
    mock_procurement_repo: MagicMock,  # noqa: F841
    mock_file_record_repo: MagicMock,  # noqa: F841
    mock_analysis_repo: MagicMock,  # noqa: F841
    mock_ai_provider: MagicMock,  # noqa: F841
    mock_gcs_provider: MagicMock,  # noqa: F841
    mock_pubsub_provider: MagicMock,  # noqa: F841
    mock_db_manager: MagicMock,  # noqa: F841
) -> None:
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

    mock_service_instance.retry_analyses.assert_called_once_with(initial_backoff_hours, max_retries, timeout_hours)
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
    mock_analysis_service: MagicMock,
    mock_budget_ledger_repo: MagicMock,  # noqa: F841
    mock_status_history_repo: MagicMock,  # noqa: F841
    mock_procurement_repo: MagicMock,  # noqa: F841
    mock_file_record_repo: MagicMock,  # noqa: F841
    mock_analysis_repo: MagicMock,  # noqa: F841
    mock_ai_provider: MagicMock,  # noqa: F841
    mock_gcs_provider: MagicMock,  # noqa: F841
    mock_pubsub_provider: MagicMock,  # noqa: F841
    mock_db_manager: MagicMock,
) -> None:
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


def test_analyze_command_missing_id() -> None:
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
    mock_analysis_service: MagicMock,
    mock_budget_ledger_repo: MagicMock,  # noqa: F841
    mock_status_history_repo: MagicMock,  # noqa: F841
    mock_procurement_repo: MagicMock,  # noqa: F841
    mock_file_record_repo: MagicMock,  # noqa: F841
    mock_analysis_repo: MagicMock,  # noqa: F841
    mock_ai_provider: MagicMock,  # noqa: F841
    mock_gcs_provider: MagicMock,  # noqa: F841
    mock_pubsub_provider: MagicMock,  # noqa: F841
    mock_db_manager: MagicMock,  # noqa: F841
) -> None:
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


# --- Tests for 'trigger-ranked-analysis' command ---
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
def test_trigger_ranked_analysis_manual_budget(
    mock_analysis_service: MagicMock,
    mock_budget_ledger_repo: MagicMock,
    mock_status_history_repo: MagicMock,
    mock_procurement_repo: MagicMock,
    mock_file_record_repo: MagicMock,
    mock_analysis_repo: MagicMock,
    mock_ai_provider: MagicMock,
    mock_gcs_provider: MagicMock,
    mock_pubsub_provider: MagicMock,
    mock_db_manager: MagicMock,
) -> None:
    """Test the trigger-ranked-analysis command with a manual budget."""
    runner = CliRunner()
    mock_service_instance = MagicMock()
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        trigger_ranked_analysis,
        [
            "--budget",
            "100.00",
        ],
    )

    mock_service_instance.run_ranked_analysis.assert_called_once()
    assert "Ranked analysis completed successfully!" in result.output
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
def test_trigger_ranked_analysis_auto_budget(
    mock_analysis_service: MagicMock,
    mock_budget_ledger_repo: MagicMock,
    mock_status_history_repo: MagicMock,
    mock_procurement_repo: MagicMock,
    mock_file_record_repo: MagicMock,
    mock_analysis_repo: MagicMock,
    mock_ai_provider: MagicMock,
    mock_gcs_provider: MagicMock,
    mock_pubsub_provider: MagicMock,
    mock_db_manager: MagicMock,
) -> None:
    """Test the trigger-ranked-analysis command with auto-budget."""
    runner = CliRunner()
    mock_service_instance = MagicMock()
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        trigger_ranked_analysis,
        [
            "--use-auto-budget",
            "--budget-period",
            "daily",
        ],
    )

    mock_service_instance.run_ranked_analysis.assert_called_once()
    assert "Ranked analysis completed successfully!" in result.output
    assert result.exit_code == 0


def test_trigger_ranked_analysis_no_budget() -> None:
    """Test that the command fails if no budget option is provided."""
    runner = CliRunner()
    result = runner.invoke(trigger_ranked_analysis, [])
    assert "Either --budget or --use-auto-budget must be provided" in result.output
    assert result.exit_code != 0


def test_trigger_ranked_analysis_auto_budget_no_period() -> None:
    """Test that the command fails if auto-budget is used without a period."""
    runner = CliRunner()
    result = runner.invoke(trigger_ranked_analysis, ["--use-auto-budget"])
    assert "--budget-period is required" in result.output
    assert result.exit_code != 0


@patch("cli.commands.DatabaseManager")
@patch("cli.commands.AnalysisService")
def test_trigger_ranked_analysis_exception(
    mock_analysis_service: MagicMock,
    mock_db_manager: MagicMock,
) -> None:
    """Test that the command handles exceptions gracefully."""
    runner = CliRunner()
    mock_service_instance = MagicMock()
    mock_service_instance.run_ranked_analysis.side_effect = Exception("Test error")
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        trigger_ranked_analysis,
        [
            "--budget",
            "100.00",
        ],
    )

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
    mock_analysis_service: MagicMock,
    mock_budget_ledger_repo: MagicMock,  # noqa: F841
    mock_status_history_repo: MagicMock,  # noqa: F841
    mock_procurement_repo: MagicMock,  # noqa: F841
    mock_file_record_repo: MagicMock,  # noqa: F841
    mock_analysis_repo: MagicMock,  # noqa: F841
    mock_ai_provider: MagicMock,  # noqa: F841
    mock_gcs_provider: MagicMock,  # noqa: F841
    mock_pubsub_provider: MagicMock,  # noqa: F841
    mock_db_manager: MagicMock,  # noqa: F841
) -> None:
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


def test_pre_analysis_command_with_invalid_date_range() -> None:
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
    mock_analysis_service: MagicMock,
    mock_budget_ledger_repo: MagicMock,  # noqa: F841
    mock_status_history_repo: MagicMock,  # noqa: F841
    mock_procurement_repo: MagicMock,  # noqa: F841
    mock_file_record_repo: MagicMock,  # noqa: F841
    mock_analysis_repo: MagicMock,  # noqa: F841
    mock_ai_provider: MagicMock,  # noqa: F841
    mock_gcs_provider: MagicMock,  # noqa: F841
    mock_pubsub_provider: MagicMock,  # noqa: F841
    mock_db_manager: MagicMock,  # noqa: F841
) -> None:
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
