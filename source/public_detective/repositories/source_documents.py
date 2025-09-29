"""This module defines the repository for handling source document data."""

import json
from uuid import UUID

from public_detective.models.source_documents import NewSourceDocument
from sqlalchemy import Engine, text


class SourceDocumentsRepository:
    """Manages data operations for source documents."""

    def __init__(self, engine: Engine) -> None:
        """Initializes the repository with its dependencies.

        Args:
            engine: The SQLAlchemy Engine for database connections.
        """
        self.engine = engine

    def save_source_document(self, source_document: NewSourceDocument) -> UUID:
        """Saves a new source document to the database and returns its ID.

        Args:
            source_document: The Pydantic model of the source document.

        Returns:
            The UUID of the newly created source document record.
        """
        sql = text(
            """
            INSERT INTO procurement_source_documents (
                analysis_id, synthetic_id, title, publication_date,
                document_type_name, url, raw_metadata
            ) VALUES (
                :analysis_id, :synthetic_id, :title, :publication_date,
                :document_type_name, :url, :raw_metadata
            )
            RETURNING id;
        """
        )
        params = {
            "analysis_id": source_document.analysis_id,
            "synthetic_id": source_document.synthetic_id,
            "title": source_document.title,
            "publication_date": source_document.publication_date,
            "document_type_name": source_document.document_type_name,
            "url": str(source_document.url) if source_document.url else None,
            "raw_metadata": json.dumps(source_document.raw_metadata),
        }
        with self.engine.connect() as conn:
            result: UUID = conn.execute(sql, parameters=params).scalar_one()
            conn.commit()
            return result
