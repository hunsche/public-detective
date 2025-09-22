"""This module contains E2E tests for file extension handling."""
import os

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import run_command


@pytest.mark.parametrize(
    "extension",
    [
        ".pdf",
        ".docx",
        ".doc",
        ".rtf",
        ".xlsx",
        ".xls",
        ".csv",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
    ],
)
def test_supported_extension_e2e(db_session: Engine, extension: str) -> None:
    """
    Tests that a procurement with a specific file extension can be processed
    end-to-end without errors related to file handling.
    """
    print(f"\n--- Starting E2E test for extension: {extension} ---")
    target_date_str = "2025-08-23"
    ibge_code = "3550308"  # São Paulo
    max_items_to_process = 1

    os.environ["TARGET_IBGE_CODES"] = f"[{ibge_code}]"
    os.environ["GCP_GEMINI_PRICE_PER_1K_TOKENS"] = "0.002"

    pre_analyze_command = (
        f"poetry run python -m public_detective.cli pre-analyze "
        f"--start-date {target_date_str} --end-date {target_date_str} "
        f"--max-messages {max_items_to_process}"
    )
    run_command(pre_analyze_command)

    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        result = connection.execute(text("SELECT analysis_id FROM procurement_analyses LIMIT 1")).scalar_one_or_none()
        assert result is not None, "No analysis record found after pre-analyze."
        analysis_id = str(result)

    analyze_command = f"poetry run python -m public_detective.cli analyze --analysis-id {analysis_id}"
    run_command(analyze_command)

    worker_command = (
        f"poetry run python -m public_detective.worker "
        f"--max-messages {max_items_to_process} "
        f"--timeout 5 "
        f"--max-output-tokens None"
    )
    run_command(worker_command)

    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        file_records = (
            connection.execute(
                text("SELECT * FROM file_records WHERE analysis_id = :analysis_id"),
                {"analysis_id": analysis_id},
            )
            .mappings()
            .all()
        )
        assert len(file_records) > 0, "No file records found for the analysis."

        for record in file_records:
            if record["file_name"].endswith(extension):
                assert record["exclusion_reason"] is None, (
                    f"File with extension {extension} was excluded "
                    f"with reason: {record['exclusion_reason']}"
                )

    print(f"--- E2E test for extension {extension} completed successfully ---")
