import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.workflows.conftest import run_command


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

        sql_not_included = text(
            """
            SELECT fr.file_name, fr.exclusion_reason
            FROM file_records fr
            JOIN procurement_source_documents psd ON fr.source_document_id = psd.id
            WHERE psd.analysis_id = :analysis_id
            AND fr.included_in_analysis IS FALSE
            ORDER BY fr.file_name
            """
        )
        not_included_results = connection.execute(sql_not_included, {"analysis_id": analysis_id}).fetchall()

        if not_included_results:
            print("--- Files not included in analysis ---")
            for file_name, exclusion_reason in not_included_results:
                reason = exclusion_reason or "(no exclusion reason recorded)"
                print(f"File: {file_name}, Reason: {reason}")
        else:
            print("--- All files marked as included in analysis ---")

        sql_all_exclusions = text(
            """
            SELECT fr.file_name, fr.exclusion_reason
            FROM file_records fr
            JOIN procurement_source_documents psd ON fr.source_document_id = psd.id
            WHERE psd.analysis_id = :analysis_id
            AND fr.exclusion_reason IS NOT NULL
            ORDER BY fr.file_name
            """
        )
        exclusion_results = connection.execute(sql_all_exclusions, {"analysis_id": analysis_id}).fetchall()

        if exclusion_results:
            print("--- Files with exclusion reasons ---")
            for file_name, exclusion_reason in exclusion_results:
                print(f"File: {file_name}, Reason: {exclusion_reason}")
        else:
            print("--- No files recorded with exclusion reasons ---")

        sql_all_files = text(
            """
            SELECT psd.id AS source_document_id,
                   fr.file_name,
                   fr.extension,
                   fr.included_in_analysis,
                   fr.exclusion_reason,
                   fr.inferred_extension,
                   fr.used_fallback_conversion
            FROM procurement_source_documents psd
            LEFT JOIN file_records fr ON fr.source_document_id = psd.id
            WHERE psd.analysis_id = :analysis_id
            ORDER BY psd.id, fr.file_name
            """
        )
        all_files_results = connection.execute(sql_all_files, {"analysis_id": analysis_id}).fetchall()

        print("--- Files and their inclusion status ---")
        if all_files_results:
            for (
                source_document_id,
                file_name,
                extension,
                included,
                exclusion_reason,
                inferred_extension,
                used_fallback,
            ) in all_files_results:
                reason = exclusion_reason or "(no exclusion reason recorded)"
                name_display = file_name or "(no file record)"
                extension_display = extension or "(unknown)"
                inferred_display = inferred_extension or "(not inferred)"
                print(
                    "SourceDocumentId: {source_document_id}, File: {name_display}, "
                    "Extension: {extension_display}, Included: {included}, Reason: {reason}, "
                    "Inferred: {inferred_display}, FallbackUsed: {used_fallback}".format(
                        source_document_id=source_document_id,
                        name_display=name_display,
                        extension_display=extension_display,
                        included=included,
                        reason=reason,
                        inferred_display=inferred_display,
                        used_fallback=used_fallback,
                    )
                )
        else:
            print("(no source documents found for this analysis)")

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
