import click

from datetime import date, datetime
from cli.services.analysis import AnalysisService
from cli.providers.date import DATE_FORMAT


@click.command()
@click.option(
    "--start-date",
    type=click.DateTime(formats=[DATE_FORMAT]),
    default=date.today().isoformat(),
    help="Start date for the analysis in YYYY-MM-DD format.",
)
@click.option(
    "--end-date",
    type=click.DateTime(formats=[DATE_FORMAT]),
    default=date.today().isoformat(),
    help="End date for the analysis in YYYY-MM-DD format.",
)
def analysis_controller(start_date: datetime, end_date: datetime):
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
        f"Analyzing data from {start_date.strftime(DATE_FORMAT)} to {end_date.strftime(DATE_FORMAT)}."
    )

    try:
        service = AnalysisService()
        service.analyze(start_date.date(), end_date.date())

        click.secho("Analysis completed successfully!", fg="green")
    except Exception as e:
        click.secho(f"An error occurred: {e}", fg="red")
