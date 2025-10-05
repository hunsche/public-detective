from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from click.testing import CliRunner
from public_detective.cli import create_cli
from public_detective.cli.analysis import analysis_group


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


class FakeProgressFactory:
    """A fake progress factory for testing."""

    calls: list[str]

    def __init__(self) -> None:
        """Initializes the fake progress factory."""
        self.calls = []

    def make(self, iterable: list[int], label: str) -> object:
        """Creates a fake progress bar.

        Args:
            iterable: The iterable to track.
            label: The label for the progress bar.

        Returns:
            A fake context manager.
        """
        self.calls.append(label)

        class _CM:
            def __enter__(self) -> list[int]:
                return iterable

            def __exit__(self, _exc_type: None, _exc: None, _tb: None) -> None:
                return

        return _CM()


@pytest.mark.parametrize(
    "should_show, no_progress_flag, expected_called",
    [
        (True, False, True),
        (False, False, False),
        (True, True, False),
    ],
)
@patch("public_detective.cli.analysis.should_show_progress")
@patch("public_detective.cli.analysis.AnalysisService")
def test_progress_bar_behavior(
    mock_analysis_service: MagicMock,
    mock_should_show_progress: MagicMock,
    should_show: bool,
    no_progress_flag: bool,
    expected_called: bool,
) -> None:
    """Tests that the progress bar is displayed based on the environment."""
    fake = FakeProgressFactory()
    mock_should_show_progress.return_value = should_show
    mock_analysis_service.return_value.run_pre_analysis.return_value = [1, 2, 3]

    with patch("public_detective.cli.analysis.PROGRESS_FACTORY", fake):
        runner = CliRunner()
        cli = create_cli()
        args = ["analysis", "prepare"]
        if no_progress_flag:
            args.append("--no-progress")
        result = runner.invoke(cli, args, color=False)
        assert result.exit_code == 0, result.output

        if no_progress_flag:
            assert not fake.calls
        else:
            assert mock_should_show_progress.called
            assert (len(fake.calls) > 0) is expected_called
