# source/job/models/procurement_model.py

from datetime import datetime
from enum import Enum, IntEnum

from pydantic import BaseModel, Field, HttpUrl


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


class Power(str, Enum):
    """Enum for government powers (poderes)."""

    EXECUTIVE = "E"
    LEGISLATIVE = "L"
    JUDICIARY = "J"
    NOT_APPLICABLE = "N"


class Sphere(str, Enum):
    """Enum for government spheres (esferas)."""

    FEDERAL = "F"
    STATE = "E"
    MUNICIPAL = "M"
    DISTRICT = "D"


class LegalSupport(BaseModel):
    """Represents the legal support for the procurement."""

    code: int = Field(..., alias="codigo")
    name: str = Field(..., alias="nome")
    description: str = Field(..., alias="descricao")


class GovernmentEntity(BaseModel):
    """Represents a government entity (órgão)."""

    cnpj: str
    name: str = Field(..., alias="razaoSocial")
    power: Power = Field(..., alias="poderId")
    sphere: Sphere = Field(..., alias="esferaId")


class EntityUnit(BaseModel):
    """Represents the administrative unit of an entity."""

    state_name: str = Field(..., alias="ufNome")
    unit_code: str = Field(..., alias="codigoUnidade")
    unit_name: str = Field(..., alias="nomeUnidade")
    state_acronym: str = Field(..., alias="ufSigla")
    municipality_name: str = Field(..., alias="municipioNome")
    ibge_code: str = Field(..., alias="codigoIbge")


class Procurement(BaseModel):
    """Represents a single procurement from the API response."""

    proposal_opening_date: datetime | None = Field(None, alias="dataAberturaProposta")
    proposal_closing_date: datetime | None = Field(None, alias="dataEncerramentoProposta")
    additional_information: str | None = Field(None, alias="informacaoComplementar")
    process_number: str = Field(..., alias="processo")
    object_description: str = Field(..., alias="objetoCompra")
    source_system_link: HttpUrl | None = Field(None, alias="linkSistemaOrigem")
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
    modality: ProcurementModality = Field(..., alias="modalidadeId")
    pncp_control_number: str = Field(..., alias="numeroControlePNCP")
    global_update_date: datetime = Field(..., alias="dataAtualizacaoGlobal")
    dispute_method: DisputeMethod = Field(..., alias="modoDisputaId")
    total_estimated_value: float | None = Field(None, alias="valorTotalEstimado")
    procurement_status: ProcurementStatus = Field(..., alias="situacaoCompraId")
    user_name: str = Field(..., alias="usuarioNome")
    electronic_process_link: HttpUrl | None = Field(None, alias="linkProcessoEletronico")
    in_person_justification: str | None = Field(None, alias="justificativaPresencial")
    budgetary_sources: list = Field([], alias="fontesOrcamentarias")


class ProcurementListResponse(BaseModel):
    """Represents the top-level structure of the procurement list API response."""

    data: list[Procurement]
    total_records: int = Field(..., alias="totalRegistros")
    total_pages: int = Field(..., alias="totalPaginas")
    page_number: int = Field(..., alias="numeroPagina")
