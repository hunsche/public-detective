"""This module defines the command-line interface (CLI) commands for the Public Detective application.

It provides functionalities to trigger, manage, and retry procurement analyses
through a set of user-friendly commands.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import click
from exceptions.analysis import AnalysisError
from models.analyses import Analysis
from providers.ai import AiProvider
from providers.database import DatabaseManager
from providers.date import DateProvider
from providers.gcs import GcsProvider
from providers.pubsub import PubSubProvider
from repositories.analyses import AnalysisRepository
from repositories.budget_ledger import BudgetLedgerRepository
from repositories.file_records import FileRecordsRepository
from repositories.procurements import ProcurementsRepository
from repositories.status_history import StatusHistoryRepository
from services.analysis import AnalysisService


@click.command("analyze")
@click.option("--analysis-id", type=UUID, required=True, help="The ID of the analysis to run.")
def analyze(analysis_id: UUID) -> None:
    """Triggers a specific procurement analysis.

    This command initiates the analysis for a single procurement
    by its unique analysis ID. It locates the corresponding record in the
    database, ensures it is in a 'PENDING_ANALYSIS' state, and then
    publishes a message to the Pub/Sub topic. A worker will then
    pick up this message to execute the full, in-depth analysis pipeline.

    Args:
        analysis_id: The unique identifier for the analysis to be processed.

    Raises:
        click.Abort: If an error occurs during the process.
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
        budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            budget_ledger_repo=budget_ledger_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
        )

        service.run_specific_analysis(analysis_id)

        click.secho("Analysis triggered successfully!", fg="green")
    except (AnalysisError, Exception) as e:
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
) -> None:
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

    Raises:
        click.BadParameter: If the start date is after the end date.
        click.Abort: If an error occurs during the process.  # noqa: DAR401, DAR402
    """
    if start_date.date() > end_date.date():
        raise click.BadParameter("Start date cannot be after end date. Please provide a valid date range.")

    import os

    import google.auth

    click.echo(f"GOOGLE_APPLICATION_CREDENTIALS: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
    try:
        credentials, project_id = google.auth.default()
        click.echo(f"Default GCP Project: {project_id}")
    except Exception as e:
        click.echo(f"Could not get default GCP project: {e}")

    click.echo(
        f"Running pre-analysis from {start_date.strftime(DateProvider.DATE_FORMAT)} to "
        f"{end_date.strftime(DateProvider.DATE_FORMAT)}."
    )

    db_engine = DatabaseManager.get_engine()
    pubsub_provider = PubSubProvider()
    gcs_provider = GcsProvider()
    ai_provider = AiProvider(Analysis)

    analysis_repo = AnalysisRepository(engine=db_engine)
    file_record_repo = FileRecordsRepository(engine=db_engine)
    procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
    status_history_repo = StatusHistoryRepository(engine=db_engine)
    budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

    service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        pubsub_provider=pubsub_provider,
    )

    try:
        service.run_pre_analysis(start_date.date(), end_date.date(), batch_size, sleep_seconds, max_messages)
        click.secho("Pre-analysis completed successfully!", fg="green")
    except (AnalysisError, Exception) as e:
        click.secho(f"An error occurred: {e}", fg="red")
        raise click.Abort()


@click.command("retry")
@click.option(
    "--initial-backoff-hours",
    type=int,
    default=6,
    help="The initial backoff period in hours for the first retry.",
    show_default=True,
)
@click.option(
    "--max-retries",
    type=int,
    default=3,
    help="The maximum number of retries for a failed analysis.",
    show_default=True,
)
@click.option(
    "--timeout-hours",
    type=int,
    default=1,
    help="The timeout in hours to consider a task stale and eligible for retry.",
    show_default=True,
)
def retry(initial_backoff_hours: int, max_retries: int, timeout_hours: int) -> None:
    """Retries failed or stale procurement analyses.

    This command identifies analyses that are in an 'ANALYSIS_FAILED' state
    or have been in the 'ANALYSIS_IN_PROGRESS' state for longer than the
    specified timeout. It then triggers a new analysis for them, respecting
    an exponential backoff strategy.

    Args:
        initial_backoff_hours: The base duration to wait before the first
            retry.
        max_retries: The maximum number of times an analysis will be
            retried.
        timeout_hours: The number of hours after which an 'IN_PROGRESS'
            task is considered stale.

    Raises:
        click.Abort: If an error occurs during the process.  # noqa: DAR401, DAR402
    """
    click.echo("Searching for analyses to retry...")

    try:
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)

        analysis_repo = AnalysisRepository(engine=db_engine)
        file_record_repo = FileRecordsRepository(engine=db_engine)
        procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
        status_history_repo = StatusHistoryRepository(engine=db_engine)
        budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            budget_ledger_repo=budget_ledger_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
        )

        retried_count = service.retry_analyses(initial_backoff_hours, max_retries, timeout_hours)

        if retried_count > 0:
            click.secho(f"Successfully triggered {retried_count} analyses for retry.", fg="green")
        else:
            click.secho("No analyses found to retry.", fg="yellow")

    except AnalysisError as e:
        click.secho(f"An error occurred while retrying analyses: {e}", fg="red")
        raise click.Abort()


@click.command("trigger-ranked-analysis")
@click.option("--budget", type=Decimal, help="The manual budget for the analysis run.")
@click.option("--use-auto-budget", is_flag=True, help="Use automatic budget calculation based on donations.")
@click.option(
    "--budget-period",
    type=click.Choice(["daily", "weekly", "monthly"]),
    help="The period for auto-budget calculation.",
)
@click.option(
    "--zero-vote-budget-percent",
    type=click.IntRange(0, 100),
    default=10,
    help="The percentage of the budget to be used for procurements with zero votes.",
    show_default=True,
)
@click.option(
    "--max-messages",
    type=int,
    default=None,
    help="Maximum number of analyses to trigger. If None, triggers all possible within budget.",
)
def trigger_ranked_analysis(
    budget: Decimal | None,
    use_auto_budget: bool,
    budget_period: str | None,
    zero_vote_budget_percent: int,
    max_messages: int | None,
) -> None:
    """Triggers a ranked analysis of pending procurements.

    Args:
        budget: The manual budget for the analysis run.
        use_auto_budget: Flag to use automatic budget calculation.
        budget_period: The period for auto-budget calculation.
        zero_vote_budget_percent: The percentage of the budget for zero-vote items.
        max_messages: Maximum number of analyses to trigger.
    """
    if not use_auto_budget and budget is None:
        raise click.UsageError("Either --budget or --use-auto-budget must be provided.")
    if use_auto_budget and not budget_period:
        raise click.UsageError("--budget-period is required when --use-auto-budget is set.")

    if use_auto_budget:
        click.echo("Triggering ranked analysis with auto-budget.")
    else:
        click.echo(f"Triggering ranked analysis with a manual budget of {budget:.2f} BRL.")

    try:
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)

        analysis_repo = AnalysisRepository(engine=db_engine)
        file_record_repo = FileRecordsRepository(engine=db_engine)
        procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
        status_history_repo = StatusHistoryRepository(engine=db_engine)
        budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            budget_ledger_repo=budget_ledger_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
        )

        # The service will handle the logic of whether to use the manual or auto budget
        service.run_ranked_analysis(
            budget=budget,
            use_auto_budget=use_auto_budget,
            budget_period=budget_period,
            zero_vote_budget_percent=zero_vote_budget_percent,
            max_messages=max_messages,
        )

        click.secho("Ranked analysis completed successfully!", fg="green")
    except Exception as e:
        click.secho(f"An error occurred: {e}", fg="red")
        raise click.Abort()
