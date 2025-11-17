"""This module defines the Pydantic models for source documents."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewSourceDocument(BaseModel):
    """Represents a new source document record to be inserted into the database.

    Attributes:
        analysis_id: The ID of the analysis this document belongs to.
        synthetic_id: The unique synthetic ID generated for this document.
        title: The original title of the document.
        publication_date: The publication date of the document.
        document_type_name: The name of the document type.
        url: The original URL of the document.
        raw_metadata: The complete raw JSON metadata for the document.
    """

    analysis_id: UUID
    synthetic_id: str
    title: str
    publication_date: datetime | None
    document_type_name: str | None
    url: str | None
    raw_metadata: dict[str, Any]


class SourceDocument(NewSourceDocument):
    """Represents a source document record read from the database."""

    model_config = ConfigDict(populate_by_name=True)

    document_id: UUID = Field(alias="id")
    created_at: datetime
    updated_at: datetime

    @property
    def id(self) -> UUID:
        """Returns the database identifier for compatibility with legacy code.

        Returns:
            The UUID primary key of the source document record.
        """
        return self.document_id
