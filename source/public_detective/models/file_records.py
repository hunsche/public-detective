"""This module defines the Pydantic models for file records.

These models are used to represent the metadata of individual files
associated with a procurement analysis, both for creating new records and
for retrieving existing ones from the database.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FileRecord(BaseModel):
    """Represents a detailed record of a single file from a procurement analysis.

    This model corresponds to a row in the `file_records` table and is used
    to store and retrieve comprehensive metadata about each file that was
    processed during an analysis run.

    Attributes:
        id: The unique identifier for the file record.
        created_at: The timestamp when the record was created.
        updated_at: The timestamp when the record was last updated.
        analysis_id: A foreign key linking this file to the specific
            `procurement_analyses` run it belongs to.
        file_name: The original name of the file.
        gcs_path: The full path to the file in Google Cloud Storage.
        extension: The file's extension (e.g., 'pdf', 'docx').
        size_bytes: The size of the file in bytes.
        nesting_level: The depth of the file if it was found inside a
            nested archive (0 for root files).
        included_in_analysis: A boolean indicating if this file was
            included in the set sent to the AI for analysis.
        exclusion_reason: If the file was not included, this field explains
            why (e.g., 'Unsupported file extension.').
        prioritization_logic: The keyword or logic used to prioritize this
            file (e.g., 'edital', 'termo de referencia').
    """

    id: UUID
    created_at: datetime
    updated_at: datetime
    analysis_id: UUID
    file_name: str
    gcs_path: str
    extension: str | None
    size_bytes: int
    nesting_level: int
    included_in_analysis: bool
    exclusion_reason: str | None
    prioritization_logic: str | None


class NewFileRecord(BaseModel):
    """Defines the data required to create a new file record.

    This model is used as a data transfer object (DTO) when creating a new
    entry in the `file_records` table. It contains all the necessary
    information that is collected before a record is persisted.
    """

    analysis_id: UUID
    file_name: str
    gcs_path: str
    extension: str | None
    size_bytes: int
    nesting_level: int
    included_in_analysis: bool
    exclusion_reason: str | None
    prioritization_logic: str | None
