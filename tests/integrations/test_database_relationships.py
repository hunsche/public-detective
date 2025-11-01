"""Integration tests for the database schema relationships."""

from public_detective.models.file_records import NewFileRecord, PrioritizationLogic
from public_detective.models.source_documents import NewSourceDocument
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.source_documents import SourceDocumentsRepository
from sqlalchemy import text
from sqlalchemy.engine import Engine


def test_database_relationships(db_session: Engine) -> None:
    """Tests the foreign key relationships between analysis, source_document, and file_record.

    Args:
        db_session: The SQLAlchemy engine.
    """
    # Arrange
    source_repo = SourceDocumentsRepository(engine=db_session)
    file_repo = FileRecordsRepository(engine=db_session)

    # Act
    # 1. Create a dummy procurement and analysis to satisfy foreign keys
    with db_session.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO procurements (pncp_control_number, version_number, raw_data, object_description,
                                          is_srp, procurement_year, procurement_sequence, pncp_publication_date,
                                          last_update_date, modality_id, procurement_status_id)
                VALUES ('test-123', 1, '{}', 'test', false, 2025, 1, NOW(), NOW(), 1, 1);
                """
            )
        )
        analysis_id = conn.execute(
            text(
                """
                INSERT INTO procurement_analyses (procurement_control_number, version_number, status)
                VALUES ('test-123', 1, 'PENDING_ANALYSIS') RETURNING analysis_id;
                """
            )
        ).scalar_one()
        conn.commit()

    # 2. Create a source document linked to the analysis
    source_doc = NewSourceDocument(
        analysis_id=analysis_id,
        synthetic_id="test-synthetic-id",
        title="Test Source Doc",
        publication_date=None,
        document_type_name="Test Type",
        url="http://example.com",
        raw_metadata={"key": "value"},
    )
    source_doc_id = source_repo.save_source_document(source_doc)

    # 3. Create a file record linked to the source document
    file_record = NewFileRecord(
        source_document_id=source_doc_id,
        file_name="test_file.txt",
        gcs_path="/fake/path",
        extension="txt",
        size_bytes=123,
        nesting_level=0,
        included_in_analysis=True,
        exclusion_reason=None,
        prioritization_logic=PrioritizationLogic.NO_PRIORITY,
        prioritization_keyword=None,
        token_limit=None,
        warnings=None,
        prepared_content_gcs_uris=None,
    )
    file_repo.save_file_record(file_record)

    # Assert
    with db_session.connect() as conn:
        # Check if the file record can be joined with the source document and analysis
        result = conn.execute(
            text(
                """
                SELECT
                    pa.analysis_id,
                    psd.id as source_doc_id,
                    fr.id as file_record_id
                FROM procurement_analyses pa
                JOIN procurement_source_documents psd ON pa.analysis_id = psd.analysis_id
                JOIN file_records fr ON psd.id = fr.source_document_id
                WHERE pa.analysis_id = :analysis_id;
                """
            ),
            {"analysis_id": analysis_id},
        ).first()

        assert result is not None
        assert result.analysis_id == analysis_id
        assert result.source_doc_id == source_doc_id
