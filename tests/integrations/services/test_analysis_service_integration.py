import json
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from PIL import Image
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.providers.ai import AiProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledgers import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcessedFile, ProcurementsRepository
from public_detective.repositories.source_documents import SourceDocumentsRepository
from public_detective.repositories.status_histories import StatusHistoryRepository
from public_detective.services.analysis import AnalysisService
from sqlalchemy import Engine, text

from tests.e2e.test_file_extensions import (
    create_docm,
    create_html,
    create_jfif,
    create_odg,
    create_pptx,
    create_txt,
    create_xlsm,
)


@pytest.fixture
def analysis_service(db_session: Any) -> AnalysisService:  # noqa: F841
    """Returns a fully initialized AnalysisService."""
    procurement_repo = Mock()
    analysis_repo = Mock()
    source_document_repo = Mock()
    file_record_repo = Mock()
    status_history_repo = Mock()
    budget_ledger_repo = Mock()
    ai_provider = Mock()
    gcs_provider = Mock()

    return AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
    )


@pytest.fixture
def integrated_analysis_service(
    db_session: Engine,
) -> AnalysisService:
    """Returns an AnalysisService instance with real repositories and mocked providers."""
    procurement_repo = ProcurementsRepository(engine=db_session, pubsub_provider=Mock(), http_provider=Mock())
    analysis_repo = AnalysisRepository(engine=db_session)
    source_document_repo = SourceDocumentsRepository(engine=db_session)
    file_record_repo = FileRecordsRepository(engine=db_session)
    status_history_repo = StatusHistoryRepository(engine=db_session)
    budget_ledger_repo = BudgetLedgerRepository(engine=db_session)
    ai_provider = MagicMock(spec=AiProvider)
    gcs_provider = MagicMock(spec=GcsProvider)
    pubsub_provider = MagicMock(spec=PubSubProvider)

    return AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        pubsub_provider=pubsub_provider,
    )


def test_prepare_ai_candidates_specialized_image_conversion(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that a TIFF file is correctly converted to PNG via the specialized image pipeline."""
    tif_path = tmp_path / "sample.tif"
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(tif_path, "tiff")

    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.tif",
        content=tif_path.read_bytes(),
        extraction_failed=False,
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".png")
    assert candidate.ai_content is not None
    assert candidate.exclusion_reason is None


def test_prepare_ai_candidates_log_file(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that .log files are correctly treated as .txt files."""
    log_path = tmp_path / "sample.log"
    log_content = "this is a log"
    create_txt(log_path, content=log_content)
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.log",
        content=log_path.read_bytes(),
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".txt")
    assert candidate.ai_content == log_content.encode()
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


def test_prepare_ai_candidates_htm_file(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that .htm files are correctly treated as .txt files."""
    htm_path = tmp_path / "sample.htm"
    create_html(htm_path)
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.htm",
        content=htm_path.read_bytes(),
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".txt")
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


def test_prepare_ai_candidates_jfif_file(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that .jfif files are correctly treated as jpeg."""
    jfif_path = tmp_path / "sample.jfif"
    create_jfif(jfif_path)
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.jfif",
        content=jfif_path.read_bytes(),
    )
    analysis_service.file_type_provider.infer_extension = Mock(return_value=".jpeg")

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".jfif")
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


@pytest.mark.parametrize(
    "extension, generator",
    [
        ("pptx", create_pptx),
        ("xlsm", create_xlsm),
        ("docm", create_docm),
        ("odg", create_odg),
    ],
)
def test_prepare_ai_candidates_office_conversion(
    analysis_service: AnalysisService,
    tmp_path: Path,
    extension: str,
    generator: Callable[[Path], None],
) -> None:
    """Tests that new Office formats are correctly converted to PDF."""
    file_path = tmp_path / f"sample.{extension}"
    generator(file_path)
    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path=f"sample.{extension}",
        content=file_path.read_bytes(),
    )

    # Mock the actual conversion to avoid dependency on LibreOffice in integration tests
    analysis_service.converter_service.convert_to_pdf = Mock(return_value=b"fake pdf content")

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".pdf")
    assert candidate.ai_content == b"fake pdf content"
    assert candidate.used_fallback_conversion is False  # It's now a direct conversion
    assert candidate.exclusion_reason is None


def test_tif_to_png_conversion(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that a .tif file is correctly converted to a .png file."""
    # Use a TIFF file, which the image converter can handle
    tif_path = tmp_path / "sample.tif"
    img = Image.new("RGB", (10, 10), color="cyan")
    img.save(tif_path, "tiff")

    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.tif",
        content=tif_path.read_bytes(),
    )

    # Mock the actual conversion to avoid dependency on ImageMagick
    analysis_service.image_converter_provider.tif_to_png = Mock(return_value=b"fake png content")

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".png")
    assert candidate.ai_content.startswith(b"\x89PNG")  # Check for PNG file signature
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


def test_prepare_ai_candidates_no_conversion_needed(analysis_service: AnalysisService, tmp_path: Path) -> None:
    """Tests that a file not requiring conversion (e.g., PDF) is handled correctly."""
    pdf_path = tmp_path / "sample.pdf"
    pdf_content = b"dummy pdf content"
    pdf_path.write_bytes(pdf_content)

    processed_file = ProcessedFile(
        source_document_id="123",
        raw_document_metadata={},
        relative_path="sample.pdf",
        content=pdf_content,
    )

    candidates = analysis_service._prepare_ai_candidates([processed_file])
    candidate = candidates[0]

    assert candidate.ai_path.endswith(".pdf")
    assert candidate.ai_content == pdf_content
    assert candidate.exclusion_reason is None
    assert candidate.used_fallback_conversion is False


def test_resume_pre_analysis_logic(integrated_analysis_service: AnalysisService, db_session: Engine) -> None:
    """
    Tests that the isolated _resume_pre_analysis logic correctly updates a stuck analysis.
    """
    # Arrange
    service = integrated_analysis_service
    control_number = "123456789"
    version = 1
    analysis_id = uuid.uuid4()
    source_doc_id = uuid.uuid4()

    raw_data_json = json.dumps(
        {
            "processo": "123/2025",
            "objetoCompra": "Test Object",
            "amparoLegal": {"codigo": 1, "nome": "Lei", "descricao": "Desc"},
            "srp": False,
            "orgaoEntidade": {
                "cnpj": "12345678000199",
                "razaoSocial": "Test Entity",
                "poderId": "E",
                "esferaId": "M",
            },
            "anoCompra": 2025,
            "sequencialCompra": 1,
            "dataPublicacaoPncp": "2025-01-01T12:00:00",
            "dataAtualizacao": "2025-01-01T12:00:00",
            "numeroCompra": "1-1-2025",
            "unidadeOrgao": {
                "ufNome": "Test State",
                "codigoUnidade": "123",
                "nomeUnidade": "Test Unit",
                "ufSigla": "TS",
                "municipioNome": "Test City",
                "codigoIbge": "1234567",
            },
            "modalidadeId": 1,
            "numeroControlePNCP": control_number,
            "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
            "modoDisputaId": 1,
            "situacaoCompraId": 1,
            "usuarioNome": "Test User",
        }
    )

    with db_session.connect() as conn:
        # 1. Create dummy procurement
        conn.execute(
            text(
                """
                INSERT INTO procurements (
                    pncp_control_number, version_number, object_description, raw_data, content_hash,
                    is_srp, procurement_year, procurement_sequence, pncp_publication_date,
                    last_update_date, modality_id, procurement_status_id
                ) VALUES (
                    :cn, :v, 'Test Object', :raw_data, 'hash',
                    false, 2025, 1, NOW(), NOW(), 1, 1
                )
                """
            ),
            {"cn": control_number, "v": version, "raw_data": raw_data_json},
        )
        # 2. Create stuck analysis record
        conn.execute(
            text(
                """
                INSERT INTO procurement_analyses (
                    analysis_id,
                    procurement_control_number,
                    version_number,
                    status,
                    document_hash
                )
                VALUES (
                    :id,
                    :cn,
                    :v,
                    :status,
                    'stuck-hash'
                )
                """
            ),
            {
                "id": analysis_id,
                "cn": control_number,
                "v": version,
                "status": ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value,
            },
        )
        # 3. Create associated source document and file record
        conn.execute(
            text(
                """
                INSERT INTO procurement_source_documents (id, analysis_id, synthetic_id, title, raw_metadata)
                VALUES (:id, :analysis_id, 'synth-1', 'doc title', '{}')
                """
            ),
            {"id": source_doc_id, "analysis_id": analysis_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO file_records (
                    source_document_id,
                    file_name,
                    gcs_path,
                    size_bytes,
                    nesting_level,
                    included_in_analysis,
                    prioritization_logic
                )
                VALUES (
                    :sd_id,
                    'test.pdf',
                    'gcs/path/test.pdf',
                    100,
                    0,
                    false,
                    'NO_PRIORITY'
                )
                """
            ),
            {"sd_id": source_doc_id},
        )
        conn.commit()

    # 4. Get the analysis object to pass to the method
    stuck_analysis = service.analysis_repo.get_analysis_by_id(analysis_id)
    assert stuck_analysis is not None
    assert stuck_analysis.status == ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value

    # 5. Mock providers
    service.ai_provider.count_tokens_for_analysis.return_value = (1000, 0, 0)

    # Act
    service._resume_pre_analysis(stuck_analysis)

    # Assert
    updated_analysis = service.analysis_repo.get_analysis_by_id(analysis_id)
    assert updated_analysis is not None
    assert updated_analysis.status == ProcurementAnalysisStatus.PENDING_ANALYSIS.value
    assert updated_analysis.input_tokens_used == 1000
    assert updated_analysis.total_cost > 0

    history = service.status_history_repo.get_history_by_analysis_id(analysis_id)
    assert len(history) == 1
    assert history[0]["status"] == ProcurementAnalysisStatus.PENDING_ANALYSIS.value
    assert "resumed" in history[0]["details"]


def test_retry_analyses_resumes_stuck_pre_analysis(
    integrated_analysis_service: AnalysisService, db_session: Engine
) -> None:
    """
    Tests that retry_analyses correctly resumes a pre-analysis stuck in PENDING_TOKEN_CALCULATION.
    """
    # Arrange
    service = integrated_analysis_service
    control_number = "123456789"
    version = 1
    stale_time = datetime.now(timezone.utc) - timedelta(hours=5)
    analysis_id = uuid.uuid4()
    source_doc_id = uuid.uuid4()

    raw_data_json = json.dumps(
        {
            "processo": "123/2025",
            "objetoCompra": "Test Object",
            "amparoLegal": {"codigo": 1, "nome": "Lei", "descricao": "Desc"},
            "srp": False,
            "orgaoEntidade": {
                "cnpj": "12345678000199",
                "razaoSocial": "Test Entity",
                "poderId": "E",
                "esferaId": "M",
            },
            "anoCompra": 2025,
            "sequencialCompra": 1,
            "dataPublicacaoPncp": "2025-01-01T12:00:00",
            "dataAtualizacao": "2025-01-01T12:00:00",
            "numeroCompra": "1-1-2025",
            "unidadeOrgao": {
                "ufNome": "Test State",
                "codigoUnidade": "123",
                "nomeUnidade": "Test Unit",
                "ufSigla": "TS",
                "municipioNome": "Test City",
                "codigoIbge": "1234567",
            },
            "modalidadeId": 1,
            "numeroControlePNCP": control_number,
            "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
            "modoDisputaId": 1,
            "situacaoCompraId": 1,
            "usuarioNome": "Test User",
        }
    )

    with db_session.connect() as conn:
        # 1. Create dummy procurement
        conn.execute(
            text(
                """
                INSERT INTO procurements (
                    pncp_control_number, version_number, object_description, raw_data, content_hash,
                    is_srp, procurement_year, procurement_sequence, pncp_publication_date,
                    last_update_date, modality_id, procurement_status_id
                ) VALUES (
                    :cn, :v, 'Test Object', :raw_data, 'hash',
                    false, 2025, 1, NOW(), NOW(), 1, 1
                )
                """
            ),
            {"cn": control_number, "v": version, "raw_data": raw_data_json},
        )
        # 2. Create stuck analysis record
        conn.execute(
            text(
                """
                INSERT INTO procurement_analyses (
                    analysis_id,
                    procurement_control_number,
                    version_number,
                    status,
                    document_hash,
                    updated_at
                )
                VALUES (
                    :id,
                    :cn,
                    :v,
                    :status,
                    'stuck-hash',
                    :stale
                )
                """
            ),
            {
                "id": analysis_id,
                "cn": control_number,
                "v": version,
                "status": ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value,
                "stale": stale_time,
            },
        )
        # 3. Create associated source document and file record
        conn.execute(
            text(
                """
                INSERT INTO procurement_source_documents (id, analysis_id, synthetic_id, title, raw_metadata)
                VALUES (:id, :analysis_id, 'synth-1', 'doc title', '{}')
                """
            ),
            {"id": source_doc_id, "analysis_id": analysis_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO file_records (
                    source_document_id,
                    file_name,
                    gcs_path,
                    size_bytes,
                    nesting_level,
                    included_in_analysis,
                    prioritization_logic
                )
                VALUES (
                    :sd_id,
                    'test.pdf',
                    'gcs/path/test.pdf',
                    100,
                    0,
                    false,
                    'NO_PRIORITY'
                )
                """
            ),
            {"sd_id": source_doc_id},
        )
        conn.commit()

    # 4. Mock providers
    service.ai_provider.count_tokens_for_analysis.return_value = (1000, 0, 0)
    service.pubsub_provider.publish = MagicMock()

    # Act
    retried_count = service.retry_analyses(initial_backoff_hours=1, max_retries=3, timeout_hours=2)

    # Assert
    assert retried_count == 1

    # Check analysis status in DB
    updated_analysis = service.analysis_repo.get_analysis_by_id(analysis_id)
    assert updated_analysis is not None
    assert updated_analysis.status == ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS.value
    assert updated_analysis.input_tokens_used == 1000
    assert updated_analysis.total_cost > 0

    # Check if it was queued for analysis
    service.pubsub_provider.publish.assert_called_once()
    publish_args = service.pubsub_provider.publish.call_args[0]
    message_data = json.loads(publish_args[1].decode())
    assert message_data["analysis_id"] == str(analysis_id)

    # Check status history
    history = service.status_history_repo.get_history_by_analysis_id(analysis_id)
    assert len(history) == 2  # PENDING_ANALYSIS, ANALYSIS_IN_PROGRESS
    assert history[0]["status"] == ProcurementAnalysisStatus.PENDING_ANALYSIS.value
    assert history[1]["status"] == ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS.value
    assert "resumed" in history[0]["details"] or "Triggering analysis" in history[1]["details"]
