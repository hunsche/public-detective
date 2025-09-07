from datetime import date, datetime
from uuid import UUID

import click
from models.analyses import Analysis
from providers.ai import AiProvider
from providers.ai_mock import MockAiProvider
from providers.config import ConfigProvider
from providers.database import DatabaseManager
from providers.date import DateProvider
from providers.gcs import GcsProvider
from providers.logging import LoggingProvider
from providers.pubsub import PubSubProvider
from repositories.analyses import AnalysisRepository
from repositories.file_records import FileRecordsRepository
from repositories.procurements import ProcurementsRepository
from repositories.status_history import StatusHistoryRepository
from services.analysis import AnalysisService


@click.command("analyze")
@click.option("--analysis-id", type=UUID, required=True, help="The ID of the analysis to run.")
def analyze(analysis_id: UUID):
    """Triggers a specific procurement analysis.

    This command initiates the analysis for a single procurement
    by its unique analysis ID. It locates the corresponding record in the
    database, ensures it is in a 'PENDING_ANALYSIS' state, and then
    publishes a message to the Pub/Sub topic. A worker will then
    pick up this message to execute the full, in-depth analysis pipeline.

    Args:
        analysis_id: The unique identifier for the analysis to be processed.
    """
    click.echo(f"Triggering analysis for analysis_id: {analysis_id}")

    try:
        config = ConfigProvider.get_config()
        logger = LoggingProvider().get_logger()

        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()

        if config.USE_AI_MOCK:
            logger.warning("Using Mock AI Provider")
            ai_provider = MockAiProvider(Analysis)
        else:
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
    """Scans for new procurements and prepares them for analysis.

    This command searches for procurements within a given date range that
    have not yet been analyzed. For each new procurement, it performs the
    following "pre-analysis" steps:
    1.  Calculates a hash of the procurement's documents to check for
        idempotency.
    2.  If the procurement is new, it saves a new version record to the
        database.
    3.  Creates a new record in the `procurement_analyses` table with a
        'PENDING_ANALYSIS' status.
    4.  Estimates the token count for the AI analysis.

    This prepares a batch of procurements for the main analysis phase, which
    can be triggered separately by the 'analyze' command or a worker.

    Args:
        start_date: The beginning of the date range to scan for new
            procurements (inclusive). Format: YYYY-MM-DD.
        end_date: The end of the date range to scan (inclusive).
            Format: YYYY-MM-DD.
        batch_size: The number of procurements to process in a single batch
            before sleeping.
        sleep_seconds: The duration in seconds to pause between batches to
            avoid overwhelming external APIs.
        max_messages: An optional limit on the total number of new analysis
            tasks to create. The process will stop once this limit is
            reached.
    """
    if start_date.date() > end_date.date():
        raise click.BadParameter("Start date cannot be after end date. Please provide a valid date range.")

    click.echo(
        f"Running pre-analysis from {start_date.strftime(DateProvider.DATE_FORMAT)} to "
        f"{end_date.strftime(DateProvider.DATE_FORMAT)}."
    )

    try:
        config = ConfigProvider.get_config()
        logger = LoggingProvider().get_logger()

        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()

        if config.USE_AI_MOCK:
            logger.warning("Using Mock AI Provider")
            ai_provider = MockAiProvider(Analysis)
        else:
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
        raise click.Abort()


@click.command("reap-stale-tasks")
@click.option(
    "--timeout-minutes",
    type=int,
    default=15,
    help="The timeout in minutes to consider a task stale.",
    show_default=True,
)
def reap_stale_tasks(timeout_minutes: int):
    """Finds and resets long-running analysis tasks.

    This command identifies analysis tasks that have been in the
    'ANALYSIS_IN_PROGRESS' state for longer than a specified timeout
    period. It then updates their status to 'TIMEOUT'.

    This is a maintenance command designed to handle cases where a worker
    might have failed unexpectedly without updating the task's final status,
    leaving it stuck. Resetting the status allows these tasks to be
    identified and potentially re-queued for analysis.

    Args:
        timeout_minutes: The number of minutes after which a task in the
            'IN_PROGRESS' state is considered stale.
    """
    click.echo(f"Searching for stale tasks with a timeout of {timeout_minutes} minutes...")

    try:
        config = ConfigProvider.get_config()
        logger = LoggingProvider().get_logger()

        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()

        if config.USE_AI_MOCK:
            logger.warning("Using Mock AI Provider")
            ai_provider = MockAiProvider(Analysis)
        else:
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
