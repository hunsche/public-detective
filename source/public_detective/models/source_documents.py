"""This module defines the Pydantic models for source documents."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


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
