from datetime import date, datetime

import click
from providers.date import DateProvider
from services.analysis import AnalysisService


@click.command()
@click.option(
    "--start-date",
    type=click.DateTime(formats=[DateProvider.DATE_FORMAT]),
    default=date.today().isoformat(),
    help="Start date for the analysis in YYYY-MM-DD format.",
)
@click.option(
    "--end-date",
    type=click.DateTime(formats=[DateProvider.DATE_FORMAT]),
    default=date.today().isoformat(),
    help="End date for the analysis in YYYY-MM-DD format.",
)
def analysis_command(start_date: datetime, end_date: datetime):
    """
    Command-line interface to run the Public Detective analysis job.

    :param start_date: The start date for the analysis.
    :param end_date: The end date for the analysis.
    """

    if start_date.date() > end_date.date():
        raise click.BadParameter(
            "Start date cannot be after end date. Please provide a valid date range."
        )

    click.echo(
        f"Analyzing data from {start_date.strftime(DateProvider.DATE_FORMAT)} to "
        f"{end_date.strftime(DateProvider.DATE_FORMAT)}."
    )

    try:
        service = AnalysisService()
        service.run_analysis(start_date.date(), end_date.date())

        click.secho("Analysis completed successfully!", fg="green")
    except Exception as e:
        click.secho(f"An error occurred: {e}", fg="red")
