"""This module defines the Pydantic models for file records.

These models are used to represent the metadata of individual files
associated with a procurement analysis, both for creating new records and
for retrieving existing ones from the database.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ExclusionReason(StrEnum):
    """Provides standardized messages for why a file was excluded from analysis."""

    UNSUPPORTED_EXTENSION = "Extensão de arquivo não suportada."
    EXTRACTION_FAILED = "Falha ao extrair o arquivo compactado. O arquivo pode estar corrompido ou protegido por senha."
    TOKEN_LIMIT_EXCEEDED = "Arquivo excluído porque o limite de {max_tokens} tokens foi excedido."  # nosec
    CONVERSION_FAILED = "Falha ao converter o arquivo."
    LOCK_FILE = "Arquivo de bloqueio temporário, ignorado pois não contém o documento real."

    def __str__(self) -> str:
        """Returns the string representation of the enum member.

        Returns:
            The string representation of the enum member.
        """
        return self.value

    def format_message(self, **kwargs: Any) -> str:
        """Formats the string with the given arguments.

        Args:
            **kwargs: The arguments to format the string with.

        Returns:
            The formatted string.
        """
        return self.value.format(**kwargs)


class PrioritizationLogic(StrEnum):
    """Provides standardized messages for why a file was prioritized."""

    BY_METADATA = "Priorizado por conter o termo '{keyword}' nos metadados."
    BY_KEYWORD = "Priorizado por conter o termo '{keyword}' no nome."
    NO_PRIORITY = "Sem priorização."

    def __str__(self) -> str:
        """Returns the string representation of the enum member.

        Returns:
            The string representation of the enum member.
        """
        return self.value

    def format_message(self, **kwargs: Any) -> str:
        """Formats the string with the given arguments.

        Args:
            **kwargs: The arguments to format the string with.

        Returns:
            The formatted string.
        """
        return self.value.format(**kwargs)


class FileRecord(BaseModel):
    """Represents a detailed record of a single file from a procurement analysis.

    This model corresponds to a row in the `file_records` table and is used
    to store and retrieve comprehensive metadata about each file that was
    processed during an analysis run.

    Attributes:
        file_record_id: The unique identifier for the file record.
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

    file_record_id: UUID
    created_at: datetime
    updated_at: datetime
    analysis_id: UUID
    file_name: str
    gcs_path: str
    extension: str | None
    size_bytes: int
    nesting_level: int
    included_in_analysis: bool
    exclusion_reason: ExclusionReason | None
    prioritization_logic: PrioritizationLogic
    prioritization_keyword: str | None
    applied_token_limit: int | None
    converted_gcs_paths: list[str] | None = None
    inferred_extension: str | None = None
    used_fallback_conversion: bool | None = None


class NewFileRecord(BaseModel):
    """Defines the data required to create a new file record.

    This model is used as a data transfer object (DTO) when creating a new
    entry in the `file_records` table. It contains all the necessary
    information that is collected before a record is persisted.
    """

    source_document_id: UUID
    file_name: str
    gcs_path: str
    extension: str | None
    size_bytes: int
    nesting_level: int
    included_in_analysis: bool
    exclusion_reason: ExclusionReason | None
    prioritization_logic: PrioritizationLogic
    prioritization_keyword: str | None
    applied_token_limit: int | None
    prepared_content_gcs_uris: list[str] | None
    inferred_extension: str | None = None
    used_fallback_conversion: bool = False
