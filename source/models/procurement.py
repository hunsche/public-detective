# source/job/models/procurement_model.py

from datetime import datetime
from enum import IntEnum, StrEnum

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
    """Enum for procurement modalities (modalidades de contratação)."""

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
    """Enum for dispute methods (modos de disputa)."""

    OPEN = 1
    CLOSED = 2
    OPEN_CLOSED = 3
    WAIVER_WITH_DISPUTE = 4
    NOT_APPLICABLE = 5
    CLOSED_OPEN = 6


class ProcurementStatus(IntEnum):
    """Enum for procurement status (situação da compra)."""

    PUBLISHED = 1
    REVOKED = 2
    ANNULLED = 3
    SUSPENDED = 4


class Power(StrEnum):
    """Enum for government powers (poderes)."""

    EXECUTIVE = "E"
    LEGISLATIVE = "L"
    JUDICIARY = "J"
    NOT_APPLICABLE = "N"


class Sphere(StrEnum):
    """Enum for government spheres (esferas)."""

    FEDERAL = "F"
    STATE = "E"
    MUNICIPAL = "M"
    DISTRICT = "D"
    NOT_APPLICABLE = "N"


class LegalSupport(BaseModel):
    """Represents the legal support for the procurement."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    code: int = Field(..., alias="codigo")
    name: str = Field(..., alias="nome")
    description: str = Field(..., alias="descricao")


class GovernmentEntity(BaseModel):
    """Represents a government entity (órgão)."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    cnpj: str
    name: str = Field(..., alias="razaoSocial")
    power: Power | str = Field(..., alias="poderId")
    sphere: Sphere | str = Field(..., alias="esferaId")


class EntityUnit(BaseModel):
    """Represents the administrative unit of an entity."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    state_name: str = Field(..., alias="ufNome")
    unit_code: str = Field(..., alias="codigoUnidade")
    unit_name: str = Field(..., alias="nomeUnidade")
    state_acronym: str = Field(..., alias="ufSigla")
    municipality_name: str = Field(..., alias="municipioNome")
    ibge_code: str = Field(..., alias="codigoIbge")


class Procurement(BaseModel):
    """Represents a single procurement from the API response."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

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
    """Represents the top-level structure of the procurement list API response."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    data: list[Procurement]
    total_records: int = Field(..., alias="totalRegistros")
    total_pages: int = Field(..., alias="totalPaginas")
    page_number: int = Field(..., alias="numeroPagina")
