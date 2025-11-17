"""This module defines the data models for AI file candidates."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from public_detective.models.file_records import ExclusionReason
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AIFileCandidate(BaseModel):
    """Represents a file being considered for AI analysis."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    synthetic_id: str
    raw_document_metadata: dict
    original_path: str
    original_content: bytes = b""
    ai_path: str = ""
    ai_content: bytes | list[bytes] = b""
    ai_gcs_uris: list[str] = Field(default_factory=list)
    prepared_content_gcs_uris: list[str] | None = None
    is_included: bool = False
    exclusion_reason: ExclusionReason | None = None
    exclusion_reason_args: dict[str, Any] = Field(default_factory=dict)
    applied_token_limit: int | None = None
    file_record_id: UUID | None = None
    extraction_failed: bool = False
    inferred_extension: str | None = None
    used_fallback_conversion: bool = False

    @model_validator(mode="after")
    def set_ai_defaults(self) -> AIFileCandidate:
        """Set the ai_path and ai_content if they're not provided.

        Returns:
            AIFileCandidate: The instance itself, with `ai_path` and `ai_content` updated if they were not provided.
        """
        if not self.ai_path:
            self.ai_path = self.original_path
        if not self.ai_content:
            self.ai_content = self.original_content
        return self
