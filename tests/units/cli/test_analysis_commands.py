from collections.abc import Iterator
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from click.testing import CliRunner
from public_detective.cli import create_cli
from public_detective.cli.analysis import analysis_group
from public_detective.cli.progress import ProgressFactory, null_spinner


# --- Tests for 'retry' command ---
@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
def test_retry_command_success(
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
    Tests that the retry command works as expected when there are analyses to retry.

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
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
        analysis_group,
        [
            "retry",
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


@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
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

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
    """
    runner = CliRunner()
    initial_backoff_hours = 6
    max_retries = 3
    timeout_hours = 1

    mock_service_instance = MagicMock()
    mock_service_instance.retry_analyses.return_value = 0
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        analysis_group,
        [
            "retry",
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
@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
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

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
    """
    runner = CliRunner()
    analysis_id = uuid4()

    mock_service_instance = MagicMock()
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(analysis_group, ["run", "--analysis-id", str(analysis_id)])
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
    result = runner.invoke(analysis_group, ["run"], catch_exceptions=False)
    assert "Missing option '--analysis-id'" in result.output
    assert result.exit_code != 0


@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
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

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
    """
    runner = CliRunner()
    analysis_id = uuid4()

    mock_service_instance = MagicMock()
    mock_service_instance.run_specific_analysis.side_effect = Exception("Test error")
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(analysis_group, ["run", "--analysis-id", str(analysis_id)])

    assert "An error occurred: Test error" in result.output
    assert result.exit_code != 0


# --- Tests for 'trigger-ranked-analysis' command ---
@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
def test_trigger_ranked_analysis_manual_budget(
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
    """Test the trigger-ranked-analysis command with a manual budget.

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
    """
    runner = CliRunner()
    mock_service_instance = MagicMock()
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        analysis_group,
        [
            "rank",
            "--budget",
            "100.00",
        ],
    )

    mock_service_instance.run_ranked_analysis.assert_called_once()
    assert "Ranked analysis completed successfully!" in result.output
    assert result.exit_code == 0


@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
def test_trigger_ranked_analysis_auto_budget(
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
    """Test the trigger-ranked-analysis command with auto-budget.

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
    """
    runner = CliRunner()
    mock_service_instance = MagicMock()
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        analysis_group,
        [
            "rank",
            "--use-auto-budget",
            "--budget-period",
            "daily",
        ],
    )

    mock_service_instance.run_ranked_analysis.assert_called_once()
    assert "Ranked analysis completed successfully!" in result.output
    assert result.exit_code == 0.0


def test_trigger_ranked_analysis_no_budget() -> None:
    """Test that the command fails if no budget option is provided."""
    runner = CliRunner()
    result = runner.invoke(analysis_group, ["rank"])
    assert "Either --budget or --use-auto-budget must be provided" in result.output
    assert result.exit_code != 0


def test_trigger_ranked_analysis_auto_budget_no_period() -> None:
    """Test that the command fails if auto-budget is used without a period."""
    runner = CliRunner()
    result = runner.invoke(analysis_group, ["rank", "--use-auto-budget"])
    assert "--budget-period is required" in result.output
    assert result.exit_code != 0


@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
def test_trigger_ranked_analysis_exception(
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
    """Test that the command handles exceptions gracefully.

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
    """
    runner = CliRunner()
    mock_service_instance = MagicMock()
    mock_service_instance.run_ranked_analysis.side_effect = Exception("Test error")
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        analysis_group,
        [
            "rank",
            "--budget",
            "100.00",
        ],
    )

    assert "An error occurred: Test error" in result.output
    assert result.exit_code != 0


# --- Tests for 'pre-analyze' command ---
@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
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

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
    """
    runner = CliRunner()
    start_date = "2025-01-01"
    end_date = "2025-01-02"
    batch_size = 50
    sleep_seconds = 30

    mock_service_instance = MagicMock()
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        analysis_group,
        [
            "prepare",
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
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 2),
        batch_size=batch_size,
        sleep_seconds=sleep_seconds,
        max_messages=None,
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
        analysis_group,
        [
            "prepare",
            "--start-date",
            start_date,
            "--end-date",
            end_date,
        ],
        catch_exceptions=False,
    )

    assert "Start date cannot be after end date." in result.output
    assert result.exit_code != 0


@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
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

    Args:
        mock_analysis_service: Mock for the AnalysisService.
        mock_budget_ledger_repo: Mock for the BudgetLedgerRepository.
        mock_status_history_repo: Mock for the StatusHistoryRepository.
        mock_procurement_repo: Mock for the ProcurementsRepository.
        mock_file_record_repo: Mock for the FileRecordsRepository.
        mock_analysis_repo: Mock for the AnalysisRepository.
        mock_ai_provider: Mock for the AiProvider.
        mock_gcs_provider: Mock for the GcsProvider.
        mock_pubsub_provider: Mock for the PubSubProvider.
        mock_db_manager: Mock for the DatabaseManager.
    """
    runner = CliRunner()
    start_date = "2025-01-01"
    end_date = "2025-01-01"

    mock_service_instance = MagicMock()
    mock_service_instance.run_pre_analysis.side_effect = Exception("Test error")
    mock_analysis_service.return_value = mock_service_instance

    result = runner.invoke(
        analysis_group,
        [
            "prepare",
            "--start-date",
            start_date,
            "--end-date",
            end_date,
        ],
    )

    assert "An error occurred: Test error" in result.output
    assert result.exit_code != 0


@pytest.mark.parametrize(
    "should_show, no_progress_flag, progress_should_run",
    [
        (True, False, True),
        (False, False, False),
        (True, True, False),
    ],
)
@patch("public_detective.cli.analysis.Progress")
@patch("public_detective.cli.analysis.should_show_progress")
@patch("public_detective.cli.analysis.AnalysisService")
def test_prepare_progress_bar_behavior(
    mock_analysis_service: MagicMock,
    mock_should_show_progress: MagicMock,
    mock_rich_progress: MagicMock,
    should_show: bool,
    no_progress_flag: bool,
    progress_should_run: bool,
) -> None:
    """Tests that the progress bar is displayed correctly for the 'prepare' command."""
    # This side effect correctly simulates the logic where the --no-progress flag
    # takes precedence over the tty/CI check.
    mock_should_show_progress.side_effect = lambda flag: should_show and not flag

    # Provide a mock generator that yields events to test the progress bar logic
    def mock_generator() -> Iterator[tuple[str, Any]]:
        yield "day_started", (date(2025, 1, 1), 1)
        yield "procurements_fetched", [1]
        yield "procurement_processed", (None, None)

    mock_analysis_service.return_value.run_pre_analysis.return_value = mock_generator()

    runner = CliRunner()
    cli = create_cli()
    args = ["analysis", "prepare"]
    if no_progress_flag:
        args.append("--no-progress")

    result = runner.invoke(cli, args, color=False)
    assert result.exit_code == 0, result.output

    assert mock_should_show_progress.called
    assert mock_rich_progress.called is progress_should_run


@patch("public_detective.cli.analysis.AnalysisService")
@patch("public_detective.cli.analysis.DatabaseManager")
def test_prepare_command_exception_handling(mock_db_manager: MagicMock, mock_analysis_service: MagicMock) -> None:
    """Tests that the prepare command handles exceptions from the service gracefully."""
    error_message = "Service failure"
    # We need to import the exception from the correct module to patch it
    from public_detective.exceptions.analysis import AnalysisError

    mock_analysis_service.return_value.run_pre_analysis.side_effect = AnalysisError(error_message)

    runner = CliRunner()
    cli = create_cli()
    result = runner.invoke(cli, ["analysis", "prepare"])

    assert result.exit_code != 0
    assert f"An error occurred: {error_message}" in result.output


def test_progress_factory_make_wraps_iterable_and_calls_click_progressbar() -> None:
    """Ensure ProgressFactory.make uses click.progressbar correctly and returns a context manager.

    This directly covers the ProgressFactory.make branch in progress.py.
    """
    data = [1, 2, 3]

    class DummyContextManager:
        def __init__(self, iterable: list[int]) -> None:
            self._iterable = iterable

        def __enter__(self) -> list[int]:
            return self._iterable

        def __exit__(self, _exception_type: Any, _exception: Any, _traceback: Any) -> None:  # noqa: ANN401
            return None

    with patch("public_detective.cli.progress.click.progressbar") as mock_progressbar:
        mock_progressbar.side_effect = lambda iterable, **kwargs: DummyContextManager(list(iterable))

        factory = ProgressFactory()
        cm = factory.make(data, label="Processing items")

        # Ensure the underlying click.progressbar was called with our options
        mock_progressbar.assert_called_once()
        _, kwargs = mock_progressbar.call_args
        assert kwargs["label"] == "Processing items"
        assert kwargs["show_pos"] is True
        assert kwargs["show_percent"] is True
        assert "%(label)s [%(bar)s] %(info)s" in kwargs["bar_template"]

        # Validate the returned context manager works and yields the iterable
        with cm as bar:
            assert list(bar) == data


def test_progress_factory_spinner_enters_and_adds_task() -> None:
    """Tests that ProgressFactory.spinner creates a Progress and adds a task with the provided label."""

    class DummyProgress:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
            self.tasks_added: list[dict[str, Any]] = []

        def __enter__(self) -> "DummyProgress":
            return self

        def __exit__(self, _exception_type: Any, _exception: Any, _traceback: Any) -> None:  # noqa: ANN401
            return None

        def add_task(self, description: str, total: Any) -> None:  # noqa: ANN401
            self.tasks_added.append({"description": description, "total": total})

    with patch("public_detective.cli.progress.Progress", DummyProgress):
        factory = ProgressFactory()
        with factory.spinner("Loading data"):
            pass

    constructed_instances: list[DummyProgress] = []

    def construct_and_capture(*args: Any, **kwargs: Any) -> DummyProgress:  # noqa: ANN401
        inst = DummyProgress(*args, **kwargs)
        constructed_instances.append(inst)
        return inst

    with patch("public_detective.cli.progress.Progress", side_effect=construct_and_capture):
        factory = ProgressFactory()
        with factory.spinner("Working..."):
            pass

    assert constructed_instances, "Expected Progress to be constructed at least once"
    # Validate that a task was added with our label and total=None
    added = constructed_instances[0].tasks_added
    assert len(added) == 1
    assert added[0]["description"] == "Working..."
    assert added[0]["total"] is None


def test_null_spinner_is_noop_context_manager() -> None:
    """Tests that null_spinner can be entered and exited without side effects or errors."""
    with null_spinner("Any label"):
        # Nothing should happen; just ensure no exceptions.
        pass


@patch("public_detective.cli.analysis.AnalysisService")
@patch("public_detective.cli.analysis.should_show_progress", return_value=True)
def test_prepare_progress_full_branches(
    _mock_should_show_progress: MagicMock, mock_analysis_service: MagicMock
) -> None:
    """Cobre os ramos de progresso do comando 'prepare':
    - day_started inicial (criação da task de dias)
    - day_started subsequente (advance no contador de dias)
    - fetching_pages_started / page_fetched / remoção de task de páginas
    - procurements_fetched (criação da task de procurements)
    - procurement_processed (advance)
    - avanço final para completar a task de dias
    """

    # Gerador de eventos que percorre múltiplos ramos
    def mock_generator() -> Iterator[tuple[str, Any]]:
        yield ("day_started", (date(2025, 1, 1), 2))
        yield ("fetching_pages_started", ("Modalidade X", 2))
        yield ("page_fetched", None)
        yield ("page_fetched", None)
        yield ("procurements_fetched", [1, 2])
        yield ("procurement_processed", (None, None))
        yield ("day_started", (date(2025, 1, 2), 2))
        yield ("procurement_processed", (None, None))

    mock_analysis_service.return_value.run_pre_analysis.return_value = mock_generator()

    # Dummy Progress que implementa a interface necessária
    class _Task:
        def __init__(self, description: str, total: int | None) -> None:
            self.description = description
            self.total = total
            self.progress = 0

        @property
        def completed(self) -> bool:
            return self.total is not None and self.progress >= self.total

    class DummyProgress:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
            self._next_id = 0
            self.tasks: dict[int, _Task] = {}
            self.added_descriptions: list[str] = []

        def __enter__(self) -> "DummyProgress":
            return self

        def __exit__(self, _exception_type: Any, _exception: Any, _traceback: Any) -> None:  # noqa: ANN401
            return None

        def add_task(self, description: str, total: int | None) -> int:
            task_id = self._next_id
            self._next_id += 1
            self.tasks[task_id] = _Task(description, total)
            self.added_descriptions.append(description)
            return task_id

        def update(self, task_id: int, advance: int = 0, description: str | None = None) -> None:
            task = self.tasks[task_id]
            if advance:
                task.progress += advance
            if description:
                task.description = description

        def remove_task(self, task_id: int) -> None:
            if task_id in self.tasks:
                del self.tasks[task_id]

    constructed: list[DummyProgress] = []

    def construct_and_capture(*args: Any, **kwargs: Any) -> DummyProgress:  # noqa: ANN401
        inst = DummyProgress(*args, **kwargs)
        constructed.append(inst)
        return inst

    with patch("public_detective.cli.analysis.Progress", side_effect=construct_and_capture):
        runner = CliRunner()
        cli = create_cli()
        result = runner.invoke(cli, ["analysis", "prepare"], color=False)

    assert result.exit_code == 0, result.output
    assert constructed, "Progress deveria ter sido instanciado"
    progress = constructed[0]

    # Verifica que a task de dias foi criada (descrição começa com "Scanning date range")
    days_task_id = next(
        (
            tid
            for tid, task in progress.tasks.items()
            if task.description.startswith("Scanning day ") or "Scanning date range" in task.description
        ),
        None,
    )
    # Após a execução, o bloco final deve ter avançado a task de dias para completar
    assert days_task_id is not None
    assert progress.tasks[days_task_id].completed is True

    # A task de páginas deve ter sido removida
    for task in progress.tasks.values():
        assert "Fetching pages for" not in task.description

    # A task de procurements foi criada durante o fluxo (pode ter sido removida depois pelo próximo day_started)
    assert any("Processing 2 procurements" in desc for desc in progress.added_descriptions)


def test_prepare_with_pncp_and_explicit_dates_fails() -> None:
    """Quando --pncp-control-number é usado com --start-date/--end-date, deve falhar com UsageError."""
    runner = CliRunner()
    cli = create_cli()
    result = runner.invoke(
        cli,
        [
            "analysis",
            "prepare",
            "--pncp-control-number",
            "BR-123",
            "--start-date",
            "2025-01-01",
        ],
        color=False,
    )
    assert result.exit_code != 0
    assert "cannot be used with --start-date or --end-date" in result.output


@patch("public_detective.cli.analysis.AnalysisService")
def test_prepare_with_only_pncp_calls_control_number_path(mock_analysis_service: MagicMock) -> None:
    """Quando somente --pncp-control-number é fornecido, deve chamar run_pre_analysis_by_control_number."""
    runner = CliRunner()
    cli = create_cli()
    result = runner.invoke(
        cli,
        [
            "analysis",
            "prepare",
            "--pncp-control-number",
            "BR-999",
        ],
        color=False,
    )
    assert result.exit_code == 0, result.output
    mock_analysis_service.return_value.run_pre_analysis_by_control_number.assert_called_once_with(
        pncp_control_number="BR-999"
    )


def test_should_show_progress_handles_isatty_exception() -> None:
    """should_show_progress deve retornar False se sys.stderr.isatty lançar exceção."""
    import sys

    from public_detective.cli.analysis import should_show_progress

    with patch.object(sys.stderr, "isatty", side_effect=RuntimeError("boom")):
        assert should_show_progress(False) is False


@patch("public_detective.cli.analysis.PROGRESS_FACTORY")
@patch("public_detective.cli.analysis.AnalysisService")
@patch("public_detective.cli.analysis.should_show_progress", return_value=True)
def test_rank_uses_progress_factory_when_should_show(
    _mock_should_show: MagicMock, mock_analysis_service: MagicMock, mock_factory: MagicMock
) -> None:
    """Quando should_show_progress é True, o comando 'rank' deve usar PROGRESS_FACTORY.make."""

    items = [1, 2, 3]
    mock_analysis_service.return_value.run_ranked_analysis.return_value = items

    class DummyCM:
        def __enter__(self) -> list[int]:
            return items

        def __exit__(self, _exception_type: Any, _exception: Any, _traceback: Any) -> None:  # noqa: ANN401
            return None

    mock_factory.make.return_value = DummyCM()

    runner = CliRunner()
    cli = create_cli()
    result = runner.invoke(cli, ["analysis", "rank", "--budget", "10.00"], color=False)

    assert result.exit_code == 0, result.output
    mock_factory.make.assert_called_once()


@patch("public_detective.cli.analysis.DatabaseManager")
@patch("public_detective.cli.analysis.PubSubProvider")
@patch("public_detective.cli.analysis.GcsProvider")
@patch("public_detective.cli.analysis.AiProvider")
@patch("public_detective.cli.analysis.AnalysisRepository")
@patch("public_detective.cli.analysis.FileRecordsRepository")
@patch("public_detective.cli.analysis.ProcurementsRepository")
@patch("public_detective.cli.analysis.StatusHistoryRepository")
@patch("public_detective.cli.analysis.BudgetLedgerRepository")
@patch("public_detective.cli.analysis.AnalysisService")
def test_retry_command_exception(
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
    """O comando 'retry' deve tratar AnalysisError e abortar com mensagem amigável."""
    from public_detective.exceptions.analysis import AnalysisError

    mock_instance = MagicMock()
    mock_instance.retry_analyses.side_effect = AnalysisError("boom")
    mock_analysis_service.return_value = mock_instance

    runner = CliRunner()
    result = runner.invoke(analysis_group, ["retry"], color=False)

    assert "An error occurred while retrying analyses" in result.output
    assert result.exit_code != 0
