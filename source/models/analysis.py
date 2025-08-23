from enum import StrEnum
from typing import Annotated, List

from pydantic import BaseModel, Field


class RedFlagCategory(StrEnum):
    """Enumeration for the categories of identified procurement risks."""

    DIRECTING = "DIRECTING"
    COMPETITION_RESTRICTION = "COMPETITION_RESTRICTION"
    OVERPRICE = "OVERPRICE"


class RedFlag(BaseModel):
    """Represents a single red flag identified during an audit.

    Attributes:
        category: The category of the irregularity.
        description: A short, objective description of the identified issue.
        evidence_quote: The exact, literal quote from the document that
                      serves as evidence for the finding.
        auditor_reasoning: A technical justification explaining why the quote
                         represents a risk.
    """

    category: RedFlagCategory = Field(
        ...,
        description="The category of the irregularity, which must be one of the allowed values.",
    )
    description: str = Field(
        ..., description="A short, objective description of the identified issue."
    )
    evidence_quote: str = Field(
        ...,
        description="The exact, literal quote from the document that serves as evidence for the finding.",
    )
    auditor_reasoning: str = Field(
        ...,
        description="A technical justification from the auditor's perspective, explaining why the quote represents a risk.",
    )


class Analysis(BaseModel):
    """Defines the structured output of a procurement document analysis.

    This model serves as the definitive schema for the analysis results,
    ensuring type safety and a predictable data structure.

    Attributes:
        risk_score: An integer from 0 to 10 representing the calculated risk.
        summary: A concise summary of the overall analysis.
        red_flags: A list of all red flag objects identified.
    """

    risk_score: int = Field(
        ...,
        description="An integer from 0 to 10 representing the calculated risk level based on the findings.",
    )
    risk_score_rationale: str = Field(
        ...,
        description="A detailed rationale (in pt-br) explaining the reasoning behind the assigned risk score.",
    )
    summary: str = Field(
        ...,
        description="A concise summary (maximum of 3 sentences, in pt-br) of the overall analysis.",
    )
    red_flags: list[RedFlag] = Field(
        default_factory=list,
        description="A list of all red flag objects identified in the document.",
    )


class AnalysisResult(BaseModel):
    """Represents the complete, persistable result of a procurement analysis.

    This model combines the original procurement identifier, the structured
    output from the AI model, any warnings generated during the file

    processing pipeline, and the storage URL of the artifact used for analysis.
    """

    procurement_control_number: str
    ai_analysis: Analysis
    gcs_document_url: str
    warnings: List[str] = []
    document_hash: str | None = None
