from datetime import date, datetime

import click
from models.analyses import Analysis
from providers.ai import AiProvider
from providers.database import DatabaseManager
from providers.date import DateProvider
from providers.gcs import GcsProvider
from providers.pubsub import PubSubProvider
from repositories.analyses import AnalysisRepository
from repositories.file_records import FileRecordsRepository
from repositories.procurements import ProcurementsRepository
from repositories.status_history import StatusHistoryRepository
from services.analysis import AnalysisService


@click.command("analyze")
@click.option("--analysis-id", type=int, required=True, help="The ID of the analysis to run.")
def analyze(analysis_id: int):
    """
    Triggers a specific Public Detective analysis job by sending a message to a queue.
    """
    click.echo(f"Triggering analysis for analysis_id: {analysis_id}")

    try:
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)

        analysis_repo = AnalysisRepository(engine=db_engine)
        file_record_repo = FileRecordsRepository(engine=db_engine)
        procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
        status_history_repo = StatusHistoryRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
        )

        service.run_specific_analysis(analysis_id)

        click.secho("Analysis triggered successfully!", fg="green")
    except Exception as e:
        click.secho(f"An error occurred: {e}", fg="red")
        raise click.Abort()


@click.command("pre-analyze")
@click.option(
    "--start-date",
    type=click.DateTime(formats=[DateProvider.DATE_FORMAT]),
    default=date.today().isoformat(),
    help="Start date for the pre-analysis in YYYY-MM-DD format.",
)
@click.option(
    "--end-date",
    type=click.DateTime(formats=[DateProvider.DATE_FORMAT]),
    default=date.today().isoformat(),
    help="End date for the pre-analysis in YYYY-MM-DD format.",
)
@click.option("--batch-size", type=int, default=100, help="Number of procurements to process in each batch.")
@click.option("--sleep-seconds", type=int, default=60, help="Seconds to sleep between batches.")
@click.option(
    "--max-messages",
    type=int,
    default=None,
    help="Maximum number of messages to publish. If None, publishes all found.",
)
def pre_analyze(
    start_date: datetime, end_date: datetime, batch_size: int, sleep_seconds: int, max_messages: int | None
):
    """
    Command-line interface to run the Public Detective pre-analysis job.
    """

    if start_date.date() > end_date.date():
        raise click.BadParameter("Start date cannot be after end date. Please provide a valid date range.")

    click.echo(
        f"Running pre-analysis from {start_date.strftime(DateProvider.DATE_FORMAT)} to "
        f"{end_date.strftime(DateProvider.DATE_FORMAT)}."
    )

    try:
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)

        analysis_repo = AnalysisRepository(engine=db_engine)
        file_record_repo = FileRecordsRepository(engine=db_engine)
        procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
        status_history_repo = StatusHistoryRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
        )

        service.run_pre_analysis(start_date.date(), end_date.date(), batch_size, sleep_seconds, max_messages)

        click.secho("Pre-analysis completed successfully!", fg="green")
    except Exception as e:
        click.secho(f"An error occurred: {e}", fg="red")


@click.command("reap-stale-tasks")
@click.option(
    "--timeout-minutes",
    type=int,
    default=15,
    help="The timeout in minutes to consider a task stale.",
    show_default=True,
)
def reap_stale_tasks(timeout_minutes: int):
    """
    Finds tasks that have been in the 'IN_PROGRESS' state for too long and
    resets them to 'TIMEOUT' status so they can be re-processed.
    """
    click.echo(f"Searching for stale tasks with a timeout of {timeout_minutes} minutes...")

    try:
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)

        analysis_repo = AnalysisRepository(engine=db_engine)
        file_record_repo = FileRecordsRepository(engine=db_engine)
        procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
        status_history_repo = StatusHistoryRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
        )

        reaped_count = service.reap_stale_analyses(timeout_minutes)

        if reaped_count > 0:
            click.secho(f"Successfully reset {reaped_count} stale tasks to TIMEOUT status.", fg="green")
        else:
            click.secho("No stale tasks found.", fg="yellow")

    except Exception as e:
        click.secho(f"An error occurred while reaping stale tasks: {e}", fg="red")
        raise click.Abort()
