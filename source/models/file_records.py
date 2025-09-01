from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FileRecord(BaseModel):
    """Represents a detailed record of a single file associated with a specific
    procurement analysis run. This model is used to store and retrieve file
    metadata from the database.

    Attributes:
        id: The unique identifier for the file record.
        created_at: The timestamp when the record was created.
        updated_at: The timestamp when the record was last updated.
        analysis_id: A foreign key linking this file record to the specific
            procurement_analyses run it belongs to.
        file_name: The original name of the file.
        gcs_path: The full path to the file in Google Cloud Storage.
        extension: The file's extension (e.g., '.pdf', '.docx').
        size_bytes: The size of the file in bytes.
        nesting_level: The depth of the file if it was found inside a nested
            archive (0 for root files).
        included_in_analysis: A boolean indicating whether this file was
            included in the set of files sent to the AI for analysis.
        exclusion_reason: If the file was not included in the analysis, this
            field provides the reason (e.g., 'Unsupported file extension.',
            'File limit exceeded.').
        prioritization_logic: The keyword or logic used to prioritize this
            file during the selection process (e.g., 'edital', 'termo de
            referencia').
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
    """Represents the data required to create a new FileRecord in the database.
    This model is used by the AnalysisService when preparing to save a new
    file's metadata.
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
