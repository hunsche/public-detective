"""This module defines the 'analysis' command group for the Public Detective CLI."""

import os
import sys
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import click
from public_detective.cli.progress import ProgressFactory, null_progress
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import Analysis
from public_detective.providers.ai import AiProvider
from public_detective.providers.database import DatabaseManager
from public_detective.providers.date import DateProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.http import HttpProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledger import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcurementsRepository
from public_detective.repositories.source_documents import SourceDocumentsRepository
from public_detective.repositories.status_history import StatusHistoryRepository
from public_detective.services.analysis import AnalysisService
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn

PROGRESS_FACTORY = ProgressFactory()


def should_show_progress(no_progress_flag: bool) -> bool:
    """Determines whether a progress bar should be displayed.

    Args:
        no_progress_flag: The value of the --no-progress flag.

    Returns:
        True if the progress bar should be shown, False otherwise.
    """
    if no_progress_flag:
        return False
    if os.getenv("CI") == "1":
        return False
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


@click.group("analysis")
@click.option(
    "--gcs-path-prefix",
    default=None,
    help="[Internal Testing] Overwrites the base GCS path for uploads.",
)
@click.pass_context
def analysis_group(ctx: click.Context, gcs_path_prefix: str | None) -> None:
    """Groups commands related to procurement analysis.

    Args:
        ctx: The click context.
        gcs_path_prefix: Overwrites the base GCS path for uploads.
    """
    ctx.obj = {"gcs_path_prefix": gcs_path_prefix}


@analysis_group.command("run")
@click.option("--analysis-id", type=UUID, required=True, help="The ID of the analysis to run.")
@click.pass_context
def run(ctx: click.Context, analysis_id: UUID) -> None:
    """Triggers a specific procurement analysis by its ID.

    Args:
        ctx: The click context.
        analysis_id: The ID of the analysis to run.
    """
    click.echo(f"Triggering analysis for analysis_id: {analysis_id}")
    gcs_path_prefix = ctx.obj.get("gcs_path_prefix")

    try:
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)
        http_provider = HttpProvider()

        analysis_repo = AnalysisRepository(engine=db_engine)
        source_document_repo = SourceDocumentsRepository(engine=db_engine)
        file_record_repo = FileRecordsRepository(engine=db_engine)
        procurement_repo = ProcurementsRepository(
            engine=db_engine, pubsub_provider=pubsub_provider, http_provider=http_provider
        )
        status_history_repo = StatusHistoryRepository(engine=db_engine)
        budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            source_document_repo=source_document_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            budget_ledger_repo=budget_ledger_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
            gcs_path_prefix=gcs_path_prefix,
        )

        service.run_specific_analysis(analysis_id)

        click.secho("Analysis triggered successfully!", fg="green")
    except (AnalysisError, Exception) as e:
        click.secho(f"An error occurred: {e}", fg="red")
        raise click.Abort()


@analysis_group.command("prepare")
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
@click.option("--no-progress", is_flag=True, help="Disable the progress bar.")
@click.pass_context
def prepare(
    ctx: click.Context,
    start_date: datetime,
    end_date: datetime,
    batch_size: int,
    sleep_seconds: int,
    max_messages: int | None,
    no_progress: bool,
) -> None:
    """Scans for new procurements and prepares them for analysis.

    Args:
        ctx: The click context.
        start_date: Start date for the pre-analysis.
        end_date: End date for the pre-analysis.
        batch_size: Number of procurements to process in each batch.
        sleep_seconds: Seconds to sleep between batches.
        max_messages: Maximum number of messages to publish.
        no_progress: Whether to disable the progress bar.
    """
    if start_date.date() > end_date.date():
        raise click.BadParameter("Start date cannot be after end date. Please provide a valid date range.")

    gcs_path_prefix = ctx.obj.get("gcs_path_prefix")
    db_engine = DatabaseManager.get_engine()
    pubsub_provider = PubSubProvider()
    gcs_provider = GcsProvider()
    ai_provider = AiProvider(Analysis)
    http_provider = HttpProvider()

    analysis_repo = AnalysisRepository(engine=db_engine)
    source_document_repo = SourceDocumentsRepository(engine=db_engine)
    file_record_repo = FileRecordsRepository(engine=db_engine)
    procurement_repo = ProcurementsRepository(
        engine=db_engine, pubsub_provider=pubsub_provider, http_provider=http_provider
    )
    status_history_repo = StatusHistoryRepository(engine=db_engine)
    budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

    service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        pubsub_provider=pubsub_provider,
        gcs_path_prefix=gcs_path_prefix,
    )

    try:
        event_generator = service.run_pre_analysis(
            start_date=start_date.date(),
            end_date=end_date.date(),
            batch_size=batch_size,
            sleep_seconds=sleep_seconds,
            max_messages=max_messages,
        )

        if not should_show_progress(no_progress):
            for _ in event_generator:
                pass
        else:
            with Progress(
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                transient=True,
            ) as progress:
                days_task_id = None
                procurements_task_id = None
                pages_task_id = None

                for event, data in event_generator:
                    if event == "day_started":
                        current_date, total_days = data
                        if days_task_id is None:
                            days_task_id = progress.add_task(
                                f"Scanning date range ({total_days} days)", total=total_days
                            )
                        else:
                            progress.update(days_task_id, advance=1)

                        progress.update(
                            days_task_id,
                            description=f"Scanning day {current_date.strftime('%Y-%m-%d')}",
                        )
                        if procurements_task_id is not None:
                            progress.remove_task(procurements_task_id)
                        procurements_task_id = None

                    elif event == "fetching_pages_started":
                        modality_name, total_pages = data
                        if pages_task_id is not None:
                            progress.remove_task(pages_task_id)
                        pages_task_id = progress.add_task(
                            f"  -> Fetching pages for {modality_name}",
                            total=total_pages,
                        )

                    elif event == "page_fetched":
                        if pages_task_id is not None:
                            progress.update(pages_task_id, advance=1)

                    elif event == "procurements_fetched":
                        if pages_task_id is not None:
                            progress.remove_task(pages_task_id)
                        pages_task_id = None

                        procurements_for_the_day = data
                        if procurements_for_the_day:
                            procurements_task_id = progress.add_task(
                                f"  -> Processing {len(procurements_for_the_day)} procurements",
                                total=len(procurements_for_the_day),
                            )

                    elif event == "procurement_processed":
                        if procurements_task_id is not None:
                            progress.update(procurements_task_id, advance=1)

                if days_task_id is not None and not progress.tasks[days_task_id].completed:
                    progress.update(days_task_id, advance=1)

        click.secho("Pre-analysis completed successfully!", fg="green")
    except (AnalysisError, Exception) as e:
        click.secho(f"An error occurred: {e}", fg="red")
        raise click.Abort()


@analysis_group.command("retry")
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
@click.pass_context
def retry(ctx: click.Context, initial_backoff_hours: int, max_retries: int, timeout_hours: int) -> None:
    """Retries failed or stale procurement analyses.

    Args:
        ctx: The click context.
        initial_backoff_hours: The initial backoff period in hours.
        max_retries: The maximum number of retries for a failed analysis.
        timeout_hours: The timeout in hours to consider a task stale.
    """
    click.echo("Searching for analyses to retry...")
    gcs_path_prefix = ctx.obj.get("gcs_path_prefix")

    try:
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)
        http_provider = HttpProvider()

        analysis_repo = AnalysisRepository(engine=db_engine)
        source_document_repo = SourceDocumentsRepository(engine=db_engine)
        file_record_repo = FileRecordsRepository(engine=db_engine)
        procurement_repo = ProcurementsRepository(
            engine=db_engine, pubsub_provider=pubsub_provider, http_provider=http_provider
        )
        status_history_repo = StatusHistoryRepository(engine=db_engine)
        budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            source_document_repo=source_document_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            budget_ledger_repo=budget_ledger_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
            gcs_path_prefix=gcs_path_prefix,
        )

        retried_count = service.retry_analyses(initial_backoff_hours, max_retries, timeout_hours)

        if retried_count > 0:
            click.secho(f"Successfully triggered {retried_count} analyses for retry.", fg="green")
        else:
            click.secho("No analyses found to retry.", fg="yellow")

    except AnalysisError as e:
        click.secho(f"An error occurred while retrying analyses: {e}", fg="red")
        raise click.Abort()


@analysis_group.command("rank")
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
@click.option("--no-progress", is_flag=True, help="Disable the progress bar.")
@click.pass_context
def rank(
    ctx: click.Context,
    budget: Decimal | None,
    use_auto_budget: bool,
    budget_period: str | None,
    zero_vote_budget_percent: int,
    max_messages: int | None,
    no_progress: bool,
) -> None:
    """Triggers a ranked analysis of pending procurements based on budget.

    Args:
        ctx: The click context.
        budget: The manual budget for the analysis run.
        use_auto_budget: Use automatic budget calculation based on donations.
        budget_period: The period for auto-budget calculation.
        zero_vote_budget_percent: Percentage of budget for zero-vote items.
        max_messages: Maximum number of analyses to trigger.
        no_progress: Whether to disable the progress bar.
    """
    if not use_auto_budget and budget is None:
        raise click.UsageError("Either --budget or --use-auto-budget must be provided.")
    if use_auto_budget and not budget_period:
        raise click.UsageError("--budget-period is required when --use-auto-budget is set.")

    if use_auto_budget:
        click.echo("Triggering ranked analysis with auto-budget.")
    else:
        click.echo(f"Triggering ranked analysis with a manual budget of {budget:.2f} BRL.")

    gcs_path_prefix = ctx.obj.get("gcs_path_prefix")

    try:
        db_engine = DatabaseManager.get_engine()
        pubsub_provider = PubSubProvider()
        gcs_provider = GcsProvider()
        ai_provider = AiProvider(Analysis)
        http_provider = HttpProvider()

        analysis_repo = AnalysisRepository(engine=db_engine)
        source_document_repo = SourceDocumentsRepository(engine=db_engine)
        file_record_repo = FileRecordsRepository(engine=db_engine)
        procurement_repo = ProcurementsRepository(
            engine=db_engine, pubsub_provider=pubsub_provider, http_provider=http_provider
        )
        status_history_repo = StatusHistoryRepository(engine=db_engine)
        budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

        service = AnalysisService(
            procurement_repo=procurement_repo,
            analysis_repo=analysis_repo,
            source_document_repo=source_document_repo,
            file_record_repo=file_record_repo,
            status_history_repo=status_history_repo,
            budget_ledger_repo=budget_ledger_repo,
            ai_provider=ai_provider,
            gcs_provider=gcs_provider,
            pubsub_provider=pubsub_provider,
            gcs_path_prefix=gcs_path_prefix,
        )

        items = service.run_ranked_analysis(
            budget=budget,
            use_auto_budget=use_auto_budget,
            budget_period=budget_period,
            zero_vote_budget_percent=zero_vote_budget_percent,
            max_messages=max_messages,
        )

        if should_show_progress(no_progress):
            cm = PROGRESS_FACTORY.make(items, label="Processing ranked analyses")
        else:
            cm = null_progress(items, label="Processing ranked analyses")

        with cm as bar:
            for _ in bar:
                pass

        click.secho("Ranked analysis completed successfully!", fg="green")
    except Exception as e:
        click.secho(f"An error occurred: {e}", fg="red")
        raise click.Abort()
