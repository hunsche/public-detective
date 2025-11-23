"""This module defines the Pydantic models for the analysis data structures."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RedFlagCategory(StrEnum):
    """Enumeration for the categories of an identified procurement risk."""

    DIRECTING = "DIRECIONAMENTO"
    COMPETITION_RESTRICTION = "RESTRICAO_COMPETITIVIDADE"
    OVERPRICE = "SOBREPRECO"
    FRAUD = "FRAUDE"
    IRREGULAR_DOCUMENTATION = "DOCUMENTACAO_IRREGULAR"
    OTHER = "OUTROS"
    SUPERFATURAMENTO = "SUPERFATURAMENTO"


class RedFlagSeverity(StrEnum):
    """Enumeration for the severity levels of an identified red flag."""

    MILD = "LEVE"
    MODERATE = "MODERADA"
    SEVERE = "GRAVE"


class SourceType(StrEnum):
    """Enumeration for the types of external sources."""

    OFFICIAL = "OFICIAL"
    INDEXED = "TABELA"
    B2B = "B2B"
    B2C = "VAREJO"


class Source(BaseModel):
    """Represents an external reference used to justify a red flag.

    Unlike the evidence quote, which comes from the procurement documents,
    sources provide supporting information from outside references. They may
    include price benchmarks, legal opinions or other materials used by the
    auditor to substantiate the finding.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(
        ...,
        description=("The name or title of the external source, e.g., 'Painel de Preços " "do Governo Federal'."),
    )
    source_type: SourceType | None = Field(
        None,
        alias="type",
        description="The classification of the source (OFFICIAL, INDEXED, B2B, B2C).",
    )
    reference_price: Decimal | None = Field(
        None,
        description="The reference price per unit obtained from the source (if available).",
    )
    price_unit: str | None = Field(
        None,
        description="The unit for the reference price, e.g., 'unit', 'meter', etc.",
    )
    reference_date: datetime | None = Field(
        None,
        description="The date when the price reference or quote was valid or collected.",
    )
    evidence: str | None = Field(
        None,
        description=("A literal snippet or quote from the source (in pt-br) supporting the price " "or irregularity."),
    )
    rationale: str | None = Field(
        None,
        description=(
            "Explanation (in pt-br) of how the source was used in the analysis; include the comparison "
            "or calculation between the contracted price and the reference price, when applicable."
        ),
    )


class RedFlag(BaseModel):
    """Represents a single red flag identified during an audit."""

    category: Literal[
        RedFlagCategory.DIRECTING,
        RedFlagCategory.COMPETITION_RESTRICTION,
        RedFlagCategory.OVERPRICE,
        RedFlagCategory.FRAUD,
        RedFlagCategory.IRREGULAR_DOCUMENTATION,
        RedFlagCategory.OTHER,
        RedFlagCategory.SUPERFATURAMENTO,
    ] = Field(
        ...,
        description=("The category of the irregularity, which must be one of the allowed values."),
    )
    severity: Literal[
        RedFlagSeverity.MILD,
        RedFlagSeverity.MODERATE,
        RedFlagSeverity.SEVERE,
    ] = Field(
        ...,
        description="The severity of the red flag, which can be 'LEVE', 'MODERADA', or 'GRAVE'.",
    )
    description: str = Field(
        ...,
        description=("A short, objective description (in pt-br) of the identified issue."),
    )
    evidence_quote: str = Field(
        ...,
        description=("The exact, literal quote from the document (in pt-br) that serves as evidence for the finding."),
    )
    auditor_reasoning: str = Field(
        ...,
        description=(
            "A technical justification (in pt-br) from the auditor's "
            "perspective, explaining why the quote represents a risk."
        ),
    )
    potential_savings: Decimal | None = Field(
        None,
        description="Estimated potential savings (unit difference * quantity) if the reference price were applied.",
    )
    sources: list[Source] | None = Field(
        None,
        description=(
            "A list of external sources used to justify the red flag. "
            "Only include this field when the category requires additional evidence (e.g., SOBREPRECO)."
        ),
    )


class GroundingSource(BaseModel):
    """Represents a source returned by the AI's grounding/search tool."""

    original_url: str = Field(..., description="The original URL returned by the search engine (may be a redirect).")
    resolved_url: str | None = Field(None, description="The resolved final URL after following redirects.")
    title: str | None = Field(None, description="The title of the page or search result.")


class Analysis(BaseModel):
    """Defines the structured output of a procurement document analysis."""

    risk_score: int | None = Field(
        None,
        ge=0,
        le=100,
        description=("An integer from 0 to 100 representing the calculated risk level based on the findings."),
    )
    risk_score_rationale: str | None = Field(
        None,
        description=("A detailed rationale (in pt-br) explaining the reasoning behind the assigned risk score."),
    )
    procurement_summary: str | None = Field(
        None,
        description="A concise summary (maximum of 3 sentences, in pt-br) of the procurement's scope.",
    )
    analysis_summary: str | None = Field(
        None,
        description="A concise summary (maximum of 3 sentences, in pt-br) of the overall analysis.",
    )
    red_flags: list[RedFlag] = Field(
        default_factory=list,
        description="A list of all red flag objects identified in the document.",
    )
    seo_keywords: list[str] = Field(
        default_factory=list,
        description="Strategic relevant keywords for SEO (in pt-br) related to the analysis.",
    )


class GroundingMetadata(BaseModel):
    """Encapsulates metadata returned by the AI's grounding/search tool."""

    search_queries: list[str] = Field(
        default_factory=list,
        description="List of search queries generated by the AI.",
    )
    sources: list[GroundingSource] = Field(
        default_factory=list,
        description="List of sources returned by the search engine.",
    )


class AnalysisResult(BaseModel):
    """Represents the complete result of a procurement analysis.

    This model combines the AI's findings with essential operational
    metadata. It serves as the primary data structure for storing and
    retrieving the outcome of an analysis from the database.

    Attributes:
        analysis_id: The unique identifier for this specific analysis record.
        procurement_control_number: The unique control number of the
            procurement from the PNCP, linking the analysis to a specific
            public notice.
        version_number: The version of the procurement data that this
            analysis was based on.
        status: The current processing status of the analysis
            (e.g., 'PENDING', 'SUCCESSFUL').
        ai_analysis: The structured analysis and red flags generated by the
            AI model.
        document_hash: A SHA-256 hash of the content of all files included
            in the analysis, used for idempotency checks.
        original_documents_gcs_path: The base GCS path (folder) where the
            original, unprocessed files for this analysis are stored.
        processed_documents_gcs_path: The GCS path for the structured JSON
            report generated by the AI model.
        input_tokens_used: The number of tokens in the prompt sent to the AI.
        output_tokens_used: The number of tokens in the response received
            from the AI.
    """

    analysis_id: UUID | None = None
    procurement_control_number: str
    version_number: int | None = None
    status: str | None = None
    retry_count: int | None = 0
    updated_at: datetime | None = None
    ai_analysis: Analysis
    document_hash: str | None = None
    original_documents_gcs_path: str | None = None
    processed_documents_gcs_path: str | None = None
    analysis_prompt: str | None = None
    input_tokens_used: int | None = None
    output_tokens_used: int | None = None
    grounding_metadata: GroundingMetadata | None = Field(
        None,
        description="Metadata returned by the AI's grounding/search tool.",
    )
    thinking_tokens_used: int | None = None
    votes_count: int | None = 0
    cost_input_tokens: Decimal | None = None
    cost_output_tokens: Decimal | None = None
    cost_thinking_tokens: Decimal | None = None
    total_cost: Decimal | None = None
