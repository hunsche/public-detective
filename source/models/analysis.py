"""
This module defines the Pydantic models for the analysis data structures.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class RedFlagCategory(StrEnum):
    """Enumeration for the categories of identified procurement risks."""

    DIRECTING = "DIRECTING"
    COMPETITION_RESTRICTION = "COMPETITION_RESTRICTION"
    OVERPRICE = "OVERPRICE"


class RedFlag(BaseModel):
    """
    Represents a single red flag identified during an audit.
    """

    category: RedFlagCategory = Field(
        ...,
        description=("The category of the irregularity, which must be one of the allowed " "values."),
    )
    description: str = Field(
        ...,
        description=("A short, objective description (in pt-br) of the identified issue."),
    )
    evidence_quote: str = Field(
        ...,
        description=("The exact, literal quote from the document that serves as evidence " "for the finding."),
    )
    auditor_reasoning: str = Field(
        ...,
        description=(
            "A technical justification (in pt-br) from the auditor's "
            "perspective, explaining why the quote represents a risk."
        ),
    )


class Analysis(BaseModel):
    """
    Defines the structured output of a procurement document analysis.
    """

    risk_score: int = Field(
        ...,
        description=("An integer from 0 to 10 representing the calculated risk level based " "on the findings."),
    )
    risk_score_rationale: str = Field(
        ...,
        description=("A detailed rationale (in pt-br) explaining the reasoning behind the " "assigned risk score."),
    )
    summary: str = Field(
        ...,
        description=("A concise summary (maximum of 3 sentences, in pt-br) of the overall " "analysis."),
    )
    red_flags: list[RedFlag] = Field(
        default_factory=list,
        description="A list of all red flag objects identified in the document.",
    )


class AnalysisResult(BaseModel):
    """
    Represents the complete, persistable result of a procurement analysis.
    """

    procurement_control_number: str
    ai_analysis: Analysis
    warnings: list[str] = []
    document_hash: str | None = None
    original_documents_url: str | None = None
    processed_documents_url: str | None = None
