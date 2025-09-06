from unittest.mock import MagicMock, patch

from cli.commands import retry
from click.testing import CliRunner


@patch("cli.commands.DatabaseManager")
@patch("cli.commands.PubSubProvider")
@patch("cli.commands.GcsProvider")
@patch("cli.commands.AiProvider")
@patch("cli.commands.AnalysisRepository")
@patch("cli.commands.FileRecordsRepository")
@patch("cli.commands.ProcurementsRepository")
@patch("cli.commands.StatusHistoryRepository")
@patch("cli.commands.AnalysisService")
def test_retry_command_success(
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
@patch("cli.commands.AnalysisService")
def test_retry_command_no_analyses(
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
