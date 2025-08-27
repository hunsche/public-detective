from datetime import date, datetime

import click
from models.analysis import Analysis
from providers.ai import AiProvider
from providers.database import DatabaseManager
from providers.date import DateProvider
from providers.gcs import GcsProvider
from providers.pubsub import PubSubProvider
from repositories.analysis import AnalysisRepository
from repositories.file_record import FileRecordRepository
from repositories.procurement import ProcurementRepository
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

    This function acts as the Composition Root for the CLI application.

    :param start_date: The start date for the analysis.
    :param end_date: The end date for the analysis.
    """

    if start_date.date() > end_date.date():
        raise click.BadParameter("Start date cannot be after end date. Please provide a valid date range.")

    click.echo(
        f"Analyzing data from {start_date.strftime(DateProvider.DATE_FORMAT)} to "
        f"{end_date.strftime(DateProvider.DATE_FORMAT)}."
    )

    try:
        # --- Dependency Injection Container ---
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)

        analysis_repo = AnalysisRepository(engine=db_engine)
        file_record_repo = FileRecordRepository(engine=db_engine)
        procurement_repo = ProcurementRepository(engine=db_engine, pubsub_provider=pubsub_provider)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            file_record_repo=file_record_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
        )
        # --- End of Container ---

        service.run_analysis(start_date.date(), end_date.date())

        click.secho("Analysis completed successfully!", fg="green")
    except Exception as e:
        click.secho(f"An error occurred: {e}", fg="red")
