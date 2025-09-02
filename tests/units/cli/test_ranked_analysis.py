from decimal import Decimal
from unittest.mock import MagicMock

from click.testing import CliRunner

from source.cli.__main__ import cli


def test_trigger_ranked_analysis_success(mocker):
    """
    Tests that the trigger-ranked-analysis command successfully invokes the
    AnalysisService with the correct budget.
    """
    mock_service_instance = MagicMock()
    mock_service_class = mocker.patch("source.cli.commands.AnalysisService", return_value=mock_service_instance)

    runner = CliRunner()
    result = runner.invoke(cli, ["trigger-ranked-analysis", "--budget", "123.45"])

    assert result.exit_code == 0
    assert "Triggering ranked analysis with a budget of 123.45 BRL." in result.output
    assert "Ranked analysis completed successfully!" in result.output

    mock_service_class.assert_called_once()
    mock_service_instance.run_ranked_analysis.assert_called_once_with(Decimal("123.45"), 100)


def test_trigger_ranked_analysis_failure(mocker):
    """
    Tests that the trigger-ranked-analysis command correctly handles exceptions
    raised by the AnalysisService.
    """
    mocker.patch(
        "source.cli.commands.AnalysisService.run_ranked_analysis",
        side_effect=Exception("Test error"),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["trigger-ranked-analysis", "--budget", "100"])

    assert result.exit_code != 0
    assert "An error occurred: Test error" in result.output
