import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import run_command


def test_debug_failed_conversion(db_session: Engine, pncp_control_number: str) -> None:
    """
    Test to debug procurements with file conversion failures using the CLI.

    This test runs the 'pre-analyze' CLI command for a specific procurement
    and then checks the database for any file conversion errors.
    """
    print(f"--- Debugging procurement via CLI: {pncp_control_number} ---")

    command = f"poetry run pd analysis prepare " f"--pncp-control-number {pncp_control_number}"

    run_command(command)

    # Verify the results in the database
    with db_session.connect() as connection:
        # Get the analysis_id for the given procurement control number
        sql_get_analysis = text(
            """
            SELECT analysis_id FROM procurement_analyses
            WHERE procurement_control_number = :pcn
            ORDER BY version_number DESC
            LIMIT 1
            """
        )
        analysis_result = connection.execute(sql_get_analysis, {"pcn": pncp_control_number}).first()
        assert analysis_result, f"No analysis found for {pncp_control_number} in the test database."
        analysis_id = analysis_result[0]

        # Check for conversion errors in file_records
        sql_check_errors = text(
            """
            SELECT fr.file_name, fr.exclusion_reason
            FROM file_records fr
            JOIN procurement_source_documents psd ON fr.source_document_id = psd.id
            WHERE psd.analysis_id = :analysis_id
            AND fr.exclusion_reason ILIKE '%convert%'
            """
        )
        error_results = connection.execute(sql_check_errors, {"analysis_id": analysis_id}).fetchall()

        if error_results:
            print("--- Conversion errors found ---")
            for row in error_results:
                print(f"File: {row[0]}, Reason: {row[1]}")
            pytest.fail(f"Conversion errors were found for {pncp_control_number} " "after running 'pre-analyze'.")
        else:
            print("--- No conversion errors found. Test passed. ---")
