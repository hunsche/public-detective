from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import numpy as np
import pytest
from public_detective.models.file_records import ExclusionReason
from public_detective.models.procurements import Procurement
from public_detective.providers.config import Config, ConfigProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.services.analysis import AIFileCandidate
from public_detective.services.pricing import PricingService
from public_detective.services.ranking import RankingService
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.fixture
def ranking_service(db_session: Engine) -> RankingService:  # noqa: F841
    """Provides a RankingService wired to the real database."""
    analysis_repo = AnalysisRepository(db_session)
    pricing_service = PricingService()
    config = ConfigProvider.get_config()
    return RankingService(analysis_repo=analysis_repo, pricing_service=pricing_service, config=config)


def _build_procurement(
    *,
    object_description: str,
    total_estimated_value: Decimal | None,
    proposal_closing_date: datetime | None,
    last_update_date: datetime,
    votes_count: int,
    sphere: str,
) -> Procurement:
    publication_date = last_update_date - timedelta(days=30)
    opening_date = (
        proposal_closing_date - timedelta(days=10) if proposal_closing_date else last_update_date - timedelta(days=10)
    )

    data = {
        "processo": f"{uuid4().hex[:8]}",
        "objetoCompra": object_description,
        "amparoLegal": {"codigo": 1, "nome": "Lei", "descricao": "Base legal"},
        "srp": False,
        "orgaoEntidade": {
            "cnpj": "00000000000191",
            "razaoSocial": "Orgão Teste",
            "poderId": "E",
            "esferaId": sphere,
        },
        "anoCompra": last_update_date.year,
        "sequencialCompra": 1,
        "dataPublicacaoPncp": publication_date.isoformat(),
        "dataAtualizacao": last_update_date.isoformat(),
        "numeroCompra": "1",
        "unidadeOrgao": {
            "ufNome": "Estado",
            "codigoUnidade": "123",
            "nomeUnidade": "Unidade",
            "ufSigla": "ST",
            "municipioNome": "Cidade",
            "codigoIbge": "1234567",
        },
        "modalidadeId": 8,
        "numeroControlePNCP": f"{uuid4().hex[:8]}-1-0001-{last_update_date.year}",
        "dataAtualizacaoGlobal": last_update_date.isoformat(),
        "modoDisputaId": 5,
        "situacaoCompraId": 1,
        "usuarioNome": "Usuario",
        "valorTotalEstimado": total_estimated_value,
        "valorTotalHomologado": total_estimated_value,
        "dataAberturaProposta": opening_date.isoformat(),
        "dataEncerramentoProposta": proposal_closing_date.isoformat() if proposal_closing_date else None,
        "fontesOrcamentarias": [],
        "linkSistemaOrigem": None,
        "linkProcessoEletronico": None,
        "justificativaPresencial": None,
    }

    procurement = Procurement.model_validate(data)
    procurement.votes_count = votes_count
    return procurement


def _build_candidate(exclusion_reason: ExclusionReason | None = None) -> AIFileCandidate:
    return AIFileCandidate(
        synthetic_id=uuid4().hex,
        raw_document_metadata={},
        original_path="edital.pdf",
        original_content=b"conteudo",
        exclusion_reason=exclusion_reason,
        is_included=exclusion_reason is None,
    )


def _persist_procurement(ranking_service: RankingService, procurement: Procurement, version_number: int) -> None:
    raw_data = procurement.model_dump_json(by_alias=True)
    modality_id = int(procurement.modality)
    procurement_status_id = int(procurement.procurement_status)

    params = {
        "pncp_control_number": procurement.pncp_control_number,
        "version_number": version_number,
        "raw_data": raw_data,
        "object_description": procurement.object_description,
        "is_srp": procurement.is_srp,
        "procurement_year": procurement.procurement_year,
        "procurement_sequence": procurement.procurement_sequence,
        "pncp_publication_date": procurement.pncp_publication_date,
        "last_update_date": procurement.last_update_date,
        "modality_id": modality_id,
        "procurement_status_id": procurement_status_id,
        "total_estimated_value": procurement.total_estimated_value,
    }

    with ranking_service.analysis_repo.engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO procurements (
                    pncp_control_number,
                    version_number,
                    raw_data,
                    object_description,
                    is_srp,
                    procurement_year,
                    procurement_sequence,
                    pncp_publication_date,
                    last_update_date,
                    modality_id,
                    procurement_status_id,
                    total_estimated_value
                ) VALUES (
                    :pncp_control_number,
                    :version_number,
                    :raw_data,
                    :object_description,
                    :is_srp,
                    :procurement_year,
                    :procurement_sequence,
                    :pncp_publication_date,
                    :last_update_date,
                    :modality_id,
                    :procurement_status_id,
                    :total_estimated_value
                )
                ON CONFLICT (pncp_control_number, version_number) DO NOTHING;
                """
            ),
            params,
        )
        conn.commit()


def _save_analysis(
    ranking_service: RankingService, procurement: Procurement, input_tokens: int, version_number: int = 1
) -> UUID:
    _persist_procurement(ranking_service, procurement, version_number)
    analysis_id: UUID = ranking_service.analysis_repo.create_pre_analysis_record(
        procurement_control_number=procurement.pncp_control_number,
        version_number=version_number,
        document_hash=uuid4().hex,
    )
    ranking_service.analysis_repo.update_pre_analysis_with_tokens(
        analysis_id=analysis_id,
        input_tokens_used=input_tokens,
        output_tokens_used=0,
        thinking_tokens_used=0,
        input_cost=Decimal("0"),
        output_cost=Decimal("0"),
        thinking_cost=Decimal("0"),
        total_cost=Decimal("0"),
        fallback_analysis_cost=Decimal("0"),
        analysis_prompt="",
    )
    return analysis_id


def _expected_priority(
    *,
    config: Config,
    potential_impact: int,
    quality_score: int,
    votes_count: int,
    estimated_cost: Decimal,
) -> int:
    vote_factor = np.log1p(votes_count)
    adjusted_impact = potential_impact * (1 + config.RANKING_WEIGHT_VOTES * vote_factor)
    priority = (
        (config.RANKING_WEIGHT_IMPACT * adjusted_impact)
        + (config.RANKING_WEIGHT_QUALITY * quality_score)
        - (config.RANKING_WEIGHT_COST * float(estimated_cost))
    )
    return int(priority)


def _extract_scores(procurement: Procurement) -> tuple[int, int, int, int, bool]:
    return (
        procurement.quality_score or 0,
        procurement.potential_impact_score or 0,
        procurement.temporal_score or 0,
        procurement.federal_bonus_score or 0,
        procurement.is_stable or False,
    )


def test_calculate_priority_combines_scores(ranking_service: RankingService) -> None:
    """Validates that all score components are applied and persisted."""
    now = datetime.now(timezone.utc)
    closing = now + timedelta(days=7)
    last_update = now - timedelta(hours=72)
    procurement = _build_procurement(
        object_description="Aquisição para saúde e educação em infraestrutura crítica",
        total_estimated_value=Decimal("2000000"),
        proposal_closing_date=closing,
        last_update_date=last_update,
        votes_count=8,
        sphere="F",
    )

    analysis_id = _save_analysis(ranking_service, procurement, input_tokens=250_000)
    candidates = [_build_candidate(), _build_candidate()]

    result = ranking_service.calculate_priority(procurement, candidates, analysis_id)

    total_cost = result.estimated_cost
    assert total_cost is not None
    quality_score, potential_impact, temporal_score, federal_bonus, is_stable = _extract_scores(result)

    assert result is procurement
    assert quality_score == 100
    assert temporal_score == 30
    assert federal_bonus == 20
    assert potential_impact == 100
    assert is_stable is True
    assert result.estimated_cost == total_cost
    assert result.last_changed_at == result.last_update_date

    expected_priority = _expected_priority(
        config=ranking_service.config,
        potential_impact=potential_impact,
        quality_score=quality_score,
        votes_count=procurement.votes_count or 0,
        estimated_cost=total_cost,
    )
    assert result.priority_score == expected_priority


def test_calculate_priority_recent_update_is_not_stable(ranking_service: RankingService) -> None:
    """Ensures stability flag reflects recent updates."""
    now = datetime.now(timezone.utc)
    closing = now + timedelta(days=6)
    last_update = now - timedelta(hours=1)
    procurement = _build_procurement(
        object_description="Aquisição geral",
        total_estimated_value=Decimal("150000"),
        proposal_closing_date=closing,
        last_update_date=last_update,
        votes_count=0,
        sphere="F",
    )

    ranking_service.calculate_priority(procurement, [_build_candidate()], None)

    assert procurement.is_stable is False
    assert procurement.last_changed_at == procurement.last_update_date


@pytest.mark.parametrize(
    "offset, expected",
    [
        (timedelta(days=7), 30),
        (timedelta(days=2), 15),
        (timedelta(days=20), 0),
        (timedelta(days=-1), 0),
        (None, 0),
    ],
)
def test_calculate_priority_temporal_windows(
    ranking_service: RankingService, offset: timedelta | None, expected: int
) -> None:
    """Confirms temporal score windows produce the configured outputs."""
    now = datetime.now(timezone.utc)
    closing = (now + offset) if offset is not None else None
    last_update = now - timedelta(hours=72)
    procurement = _build_procurement(
        object_description="Aquisição padrão",
        total_estimated_value=Decimal("0"),
        proposal_closing_date=closing,
        last_update_date=last_update,
        votes_count=0,
        sphere="M",
    )

    ranking_service.calculate_priority(procurement, [_build_candidate()], None)

    assert procurement.temporal_score == expected


def test_calculate_priority_quality_penalties_applied(ranking_service: RankingService) -> None:
    """Validates compound penalties and ratio adjustments for quality scoring."""
    now = datetime.now(timezone.utc)
    last_update = now - timedelta(hours=72)
    procurement = _build_procurement(
        object_description="Aquisição genérica",
        total_estimated_value=None,
        proposal_closing_date=None,
        last_update_date=last_update,
        votes_count=0,
        sphere="M",
    )

    candidates = [
        _build_candidate(ExclusionReason.EXTRACTION_FAILED),
        _build_candidate(ExclusionReason.CONVERSION_FAILED),
        _build_candidate(ExclusionReason.UNSUPPORTED_EXTENSION),
        _build_candidate(None),
    ]

    ranking_service.calculate_priority(procurement, candidates, None)

    assert procurement.quality_score == 35
    assert procurement.potential_impact_score == 0
    assert procurement.priority_score == int(ranking_service.config.RANKING_WEIGHT_QUALITY * 35)


def test_calculate_priority_no_candidates_results_in_zero_quality(ranking_service: RankingService) -> None:
    """Checks that empty candidate lists yield zero quality."""
    now = datetime.now(timezone.utc)
    last_update = now - timedelta(hours=72)
    procurement = _build_procurement(
        object_description="Aquisição genérica",
        total_estimated_value=None,
        proposal_closing_date=None,
        last_update_date=last_update,
        votes_count=0,
        sphere="M",
    )

    ranking_service.calculate_priority(procurement, [], None)

    assert procurement.quality_score == 0
    assert procurement.priority_score == 0


def test_calculate_priority_potential_impact_is_capped(ranking_service: RankingService) -> None:
    """Ensures the potential impact score respects the maximum cap."""
    now = datetime.now(timezone.utc)
    closing = now + timedelta(days=8)
    last_update = now - timedelta(hours=72)
    procurement = _build_procurement(
        object_description="Projeto de saúde educação e infraestrutura crítica",
        total_estimated_value=Decimal("5000000"),
        proposal_closing_date=closing,
        last_update_date=last_update,
        votes_count=0,
        sphere="F",
    )

    ranking_service.calculate_priority(procurement, [_build_candidate()], None)

    assert procurement.potential_impact_score == 100


def test_calculate_priority_non_federal_has_no_bonus(ranking_service: RankingService) -> None:
    """Verifies that only federal procurements receive the federal bonus."""
    now = datetime.now(timezone.utc)
    closing = now + timedelta(days=7)
    last_update = now - timedelta(hours=72)
    procurement = _build_procurement(
        object_description="Aquisição municipal",
        total_estimated_value=Decimal("800000"),
        proposal_closing_date=closing,
        last_update_date=last_update,
        votes_count=0,
        sphere="M",
    )

    ranking_service.calculate_priority(procurement, [_build_candidate()], None)

    assert procurement.federal_bonus_score == 0


def test_calculate_priority_cost_penalizes_priority(ranking_service: RankingService) -> None:
    """Confirms that high estimated costs reduce the aggregated priority score."""
    now = datetime.now(timezone.utc)
    last_update = now - timedelta(hours=72)
    procurement = _build_procurement(
        object_description="Aquisição de baixo impacto",
        total_estimated_value=Decimal("0"),
        proposal_closing_date=None,
        last_update_date=last_update,
        votes_count=0,
        sphere="M",
    )

    analysis_id = _save_analysis(ranking_service, procurement, input_tokens=100_000_000)

    ranking_service.calculate_priority(procurement, [_build_candidate()], analysis_id)

    total_cost = procurement.estimated_cost
    assert total_cost is not None
    expected_priority = _expected_priority(
        config=ranking_service.config,
        potential_impact=0,
        quality_score=100,
        votes_count=0,
        estimated_cost=total_cost,
    )

    assert procurement.estimated_cost == total_cost
    assert procurement.priority_score == expected_priority
    assert procurement.priority_score < 0


def test_calculate_priority_missing_analysis_falls_back_to_zero_cost(ranking_service: RankingService) -> None:
    """Ensures missing analysis records do not cause failures and default to zero cost."""
    now = datetime.now(timezone.utc)
    last_update = now - timedelta(hours=72)
    procurement = _build_procurement(
        object_description="Aquisição padrão",
        total_estimated_value=Decimal("100000"),
        proposal_closing_date=None,
        last_update_date=last_update,
        votes_count=1,
        sphere="F",
    )

    ranking_service.calculate_priority(procurement, [_build_candidate()], uuid4())

    assert procurement.estimated_cost == Decimal("0.0")
