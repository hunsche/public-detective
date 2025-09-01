"""This module defines the Pydantic models for representing procurement data.

These models are designed to align with the data structures returned by the
PNCP (Plataforma Nacional de Contratações Públicas) API. They include
enumerations for various coded values (e.g., document types, modalities)
and comprehensive models for procurements, their associated documents, and
other related entities.
"""
from datetime import datetime
from enum import IntEnum, StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class DocumentType(IntEnum):
    """Enumeration for document types (Tipo de Documento).

    Defines the various types of documents that can be attached to a
    procurement, as detailed in section 5.12 of the PNCP integration manual.
    """

    DIRECT_CONTRACTING_NOTICE = 1
    BID_NOTICE = 2
    CONTRACT_DRAFT = 3
    TERMS_OF_REFERENCE = 4
    PRELIMINARY_DRAFT = 5
    BASIC_PROJECT = 6
    PRELIMINARY_TECHNICAL_STUDY = 7
    EXECUTIVE_PROJECT = 8
    RISK_MATRIX = 9
    DFD = 10
    PRICE_REGISTRATION_ACT = 11
    CONTRACT = 12
    TERMINATION_AGREEMENT = 13
    ADDITIVE_AGREEMENT = 14
    AMENDMENT_AGREEMENT = 15
    OTHER_DOCUMENTS = 16
    PAYMENT_COMMITMENT_NOTE = 17


class ProcurementDocument(BaseModel):
    """Represents a single document associated with a procurement.

    This model is based on the response structure of the
    /orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos endpoint,
    detailed in section 6.3.8 of the PNCP integration manual.
    """

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    uri: HttpUrl | str | None = None
    url: HttpUrl | str | None = None
    document_sequence: int = Field(..., alias="sequencialDocumento")
    publication_date: datetime = Field(..., alias="dataPublicacaoPncp")
    cnpj: str
    procurement_year: int = Field(..., alias="anoCompra")
    procurement_sequence: int = Field(..., alias="sequencialCompra")
    is_active: bool = Field(..., alias="statusAtivo")
    title: str = Field(..., alias="titulo")
    document_type_id: DocumentType | int = Field(..., alias="tipoDocumentoId")
    document_type_name: str = Field(..., alias="tipoDocumentoNome")
    document_type_description: str = Field(..., alias="tipoDocumentoDescricao")


class ProcurementModality(IntEnum):
    """Enumeration for procurement modalities (modalidades de contratação)."""

    ELECTRONIC_AUCTION = 1
    COMPETITIVE_DIALOGUE = 2
    CONTEST = 3
    ELECTRONIC_COMPETITION = 4
    IN_PERSON_COMPETITION = 5
    ELECTRONIC_REVERSE_AUCTION = 6
    IN_PERSON_REVERSE_AUCTION = 7
    BIDDING_WAIVER = 8
    BIDDING_UNENFORCEABILITY = 9
    EXPRESSION_OF_INTEREST = 10
    PRE_QUALIFICATION = 11
    ACCREDITATION = 12
    IN_PERSON_AUCTION = 13


class DisputeMethod(IntEnum):
    """Enumeration for dispute methods (modos de disputa)."""

    OPEN = 1
    CLOSED = 2
    OPEN_CLOSED = 3
    WAIVER_WITH_DISPUTE = 4
    NOT_APPLICABLE = 5
    CLOSED_OPEN = 6


class ProcurementStatus(IntEnum):
    """Enumeration for the status of a procurement (situação da compra)."""

    PUBLISHED = 1
    REVOKED = 2
    ANNULLED = 3
    SUSPENDED = 4


class Power(StrEnum):
    """Enumeration for government powers (poderes)."""

    EXECUTIVE = "E"
    LEGISLATIVE = "L"
    JUDICIARY = "J"
    NOT_APPLICABLE = "N"


class Sphere(StrEnum):
    """Enumeration for government spheres (esferas)."""

    FEDERAL = "F"
    STATE = "E"
    MUNICIPAL = "M"
    DISTRICT = "D"
    NOT_APPLICABLE = "N"


class LegalSupport(BaseModel):
    """Details the legal basis for the procurement process.

    Attributes:
        code: The numeric code for the legal provision.
        name: The name of the legal provision (e.g., 'Lei nº 14.133/2021').
        description: A description of the legal provision.
    """

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    code: int = Field(..., alias="codigo")
    name: str = Field(..., alias="nome")
    description: str = Field(..., alias="descricao")


class GovernmentEntity(BaseModel):
    """Represents a government entity (órgão) responsible for the procurement.

    Attributes:
        cnpj: The CNPJ (taxpayer ID) of the entity.
        name: The official name of the government entity.
        power: The branch of government (Executive, Legislative, etc.).
        sphere: The level of government (Federal, State, Municipal).
    """

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    cnpj: str
    name: str = Field(..., alias="razaoSocial")
    power: Power | str = Field(..., alias="poderId")
    sphere: Sphere | str = Field(..., alias="esferaId")


class EntityUnit(BaseModel):
    """Represents the specific administrative unit within a government entity.

    Attributes:
        state_name: The name of the state.
        unit_code: The specific code of the administrative unit.
        unit_name: The name of the administrative unit.
        state_acronym: The acronym of the state (e.g., 'SP', 'RJ').
        municipality_name: The name of the municipality.
        ibge_code: The IBGE (Brazilian Institute of Geography and Statistics)
            code for the municipality.
    """

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    state_name: str = Field(..., alias="ufNome")
    unit_code: str = Field(..., alias="codigoUnidade")
    unit_name: str = Field(..., alias="nomeUnidade")
    state_acronym: str = Field(..., alias="ufSigla")
    municipality_name: str = Field(..., alias="municipioNome")
    ibge_code: str = Field(..., alias="codigoIbge")


class Procurement(BaseModel):
    """Represents a single, detailed procurement record from the PNCP API.

    This model captures all the core information about a public procurement
    process, including dates, values, responsible parties, and legal details.

    Attributes:
        procurement_id: The internal unique identifier for the procurement
            record in the local database.
        proposal_opening_date: The date and time when proposals are opened.
        proposal_closing_date: The deadline for submitting proposals.
        additional_information: Any supplementary information provided.
        process_number: The official number of the administrative process.
        object_description: A description of what is being procured.
        source_system_link: A URL to the procurement in the source system.
        legal_support: The legal basis for the procurement.
        total_awarded_value: The final value at which the contract was
            awarded.
        is_srp: A boolean indicating if it is a Price Registration System
            (Sistema de Registro de Preços).
        government_entity: The government entity conducting the procurement.
        procurement_year: The year the procurement was initiated.
        procurement_sequence: The sequential number of the procurement within
            the year for that entity.
        pncp_publication_date: The date the procurement was published on PNCP.
        last_update_date: The date the procurement was last updated on PNCP.
        procurement_number: The full formatted number of the procurement.
        entity_unit: The specific administrative unit managing the procurement.
        modality: The procurement modality (e.g., Auction, Competition).
        pncp_control_number: The unique control number assigned by PNCP.
        global_update_date: The timestamp of the last global update for this
            record.
        dispute_method: The method used for dispute resolution.
        total_estimated_value: The estimated total value of the procurement.
        procurement_status: The current status (e.g., Published, Revoked).
        user_name: The name of the user who registered the procurement.
        electronic_process_link: A URL to the electronic process system.
        in_person_justification: Justification if the process is not
            electronic.
        budgetary_sources: A list of budgetary sources for the procurement.
    """

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    procurement_id: UUID | None = None
    proposal_opening_date: datetime | None = Field(None, alias="dataAberturaProposta")
    proposal_closing_date: datetime | None = Field(None, alias="dataEncerramentoProposta")
    additional_information: str | None = Field(None, alias="informacaoComplementar")
    process_number: str = Field(..., alias="processo")
    object_description: str = Field(..., alias="objetoCompra")
    source_system_link: HttpUrl | str | None = Field(None, alias="linkSistemaOrigem")
    legal_support: LegalSupport = Field(..., alias="amparoLegal")
    total_awarded_value: float | None = Field(None, alias="valorTotalHomologado")
    is_srp: bool = Field(..., alias="srp")
    government_entity: GovernmentEntity = Field(..., alias="orgaoEntidade")
    procurement_year: int = Field(..., alias="anoCompra")
    procurement_sequence: int = Field(..., alias="sequencialCompra")
    pncp_publication_date: datetime = Field(..., alias="dataPublicacaoPncp")
    last_update_date: datetime = Field(..., alias="dataAtualizacao")
    procurement_number: str = Field(..., alias="numeroCompra")
    entity_unit: EntityUnit = Field(..., alias="unidadeOrgao")
    modality: ProcurementModality | int = Field(..., alias="modalidadeId")
    pncp_control_number: str = Field(..., alias="numeroControlePNCP")
    global_update_date: datetime = Field(..., alias="dataAtualizacaoGlobal")
    dispute_method: DisputeMethod | int = Field(..., alias="modoDisputaId")
    total_estimated_value: float | None = Field(None, alias="valorTotalEstimado")
    procurement_status: ProcurementStatus | int = Field(..., alias="situacaoCompraId")
    user_name: str = Field(..., alias="usuarioNome")
    electronic_process_link: HttpUrl | str | None = Field(None, alias="linkProcessoEletronico")
    in_person_justification: str | None = Field(None, alias="justificativaPresencial")
    budgetary_sources: list = Field([], alias="fontesOrcamentarias")


class ProcurementListResponse(BaseModel):
    """Represents the paginated response from the procurement list endpoint.

    This model captures the top-level structure of the API response,
    including the list of procurement records for the current page and
    pagination metadata.

    Attributes:
        data: A list of `Procurement` objects for the current page.
        total_records: The total number of records available across all pages.
        total_pages: The total number of pages available.
        page_number: The number of the current page.
    """

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    data: list[Procurement]
    total_records: int = Field(..., alias="totalRegistros")
    total_pages: int = Field(..., alias="totalPaginas")
    page_number: int = Field(..., alias="numeroPagina")
