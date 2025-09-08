from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from public_detective.cli.commands import retry


def test_retry_command_no_analyses() -> None:
    """
    Tests that the retry command handles the case where no analyses are found.
    """
    with patch("public_detective.cli.commands.AnalysisService") as mock_analysis_service:
        mock_service_instance = MagicMock()
        mock_service_instance.retry_analyses.return_value = 0
        mock_analysis_service.return_value = mock_service_instance

        runner = CliRunner()
        result = runner.invoke(retry)

        assert result.exit_code == 0
        assert "No analyses found to retry." in result.output


def test_retry_command_with_analyses() -> None:
    """
    Tests the retry command when analyses are found and retried.
    """
    with patch("public_detective.cli.commands.AnalysisService") as mock_analysis_service:
        mock_service_instance = MagicMock()
        mock_service_instance.retry_analyses.return_value = 5
        mock_analysis_service.return_value = mock_service_instance

        runner = CliRunner()
        result = runner.invoke(retry)

        assert result.exit_code == 0
        assert "Successfully triggered 5 analyses for retry." in result.output
