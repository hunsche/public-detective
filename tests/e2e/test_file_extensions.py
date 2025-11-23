"This module contains E2E tests for file extension handling."

import json
import shutil
import subprocess  # nosec B404
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from public_detective.models.analyses import Analysis
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.providers.ai import AiProvider
from public_detective.providers.config import ConfigProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.http import HttpProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledgers import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcessedFile, ProcurementsRepository
from public_detective.repositories.source_documents import SourceDocumentsRepository
from public_detective.repositories.status_histories import StatusHistoryRepository
from public_detective.services.analysis import AnalysisService
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.conftest import GcsCleanupManager, MockPNCP, run_command


# Helper functions to generate files
def create_txt(path: Path, content: str = "This is a test text file.") -> None:
    """Creates a simple text file.

    Args:
        path: The path to the file.
        content: The content of the file.
    """
    path.write_text(content)


def create_doc(path: Path) -> None:
    """Copies a valid DOC file from the fixtures directory.

    Args:
        path: The path to the file.
    """
    fixture_path = Path(__file__).parent.parent / "fixtures" / "file_samples" / "valid_test.doc"
    shutil.copy(fixture_path, path)


def create_docx(path: Path, content: str = "This is a test DOCX file.") -> None:
    """Creates a simple DOCX file using LibreOffice conversion."""
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        source_path = tmp_dir / "input.rtf"
        create_rtf(source_path, content)
        user_profile = tmp_dir / "lo-profile"
        user_profile.mkdir(parents=True, exist_ok=True)
        cmd = [
            "soffice",
            "--headless",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
            "--invisible",
            f"-env:UserInstallation=file://{user_profile.resolve()}",
            "--convert-to",
            "docx:MS Word 2007 XML",
            "--outdir",
            str(tmp_dir),
            str(source_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603
        if completed.returncode != 0:
            raise RuntimeError(f"LibreOffice failed to create DOCX: {completed.stderr[:500]}")
        generated_path = tmp_dir / "input.docx"
        if not generated_path.exists():
            raise RuntimeError("LibreOffice did not generate the expected DOCX file.")
        shutil.copy(generated_path, path)


def create_odt(path: Path, content: str = "This is a test ODT file.") -> None:
    """Creates a simple ODT file using LibreOffice conversion."""

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        source_path = tmp_dir / "input.docx"
        create_docx(source_path, content)
        user_profile = tmp_dir / "lo-profile"
        user_profile.mkdir(parents=True, exist_ok=True)
        cmd = [
            "soffice",
            "--headless",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
            "--invisible",
            f"-env:UserInstallation=file://{user_profile}",
            "--convert-to",
            "odt",
            "--outdir",
            str(tmp_dir),
            str(source_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603
        if completed.returncode != 0:
            raise RuntimeError(f"LibreOffice failed to create ODT: {completed.stderr[:500]}")
        generated_path = tmp_dir / "input.odt"
        if not generated_path.exists():
            raise RuntimeError("LibreOffice did not generate the expected ODT file.")
        shutil.copy(generated_path, path)


def create_xls(path: Path) -> None:
    """Creates a simple XLS file using LibreOffice conversion."""

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        source_path = tmp_dir / "input.csv"
        create_csv(source_path)
        user_profile = tmp_dir / "lo-profile"
        user_profile.mkdir(parents=True, exist_ok=True)
        cmd = [
            "soffice",
            "--headless",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
            "--invisible",
            f"-env:UserInstallation=file://{user_profile}",
            "--convert-to",
            "xls",
            "--outdir",
            str(tmp_dir),
            str(source_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603
        if completed.returncode != 0:
            raise RuntimeError(f"LibreOffice failed to create XLS: {completed.stderr[:500]}")
        generated_path = tmp_dir / "input.xls"
        if not generated_path.exists():
            raise RuntimeError("LibreOffice did not generate the expected XLS file.")
        shutil.copy(generated_path, path)


def create_xlsx(path: Path) -> None:
    """Creates a simple XLSX file using LibreOffice conversion."""

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        source_path = tmp_dir / "input.csv"
        create_csv(source_path)
        user_profile = tmp_dir / "lo-profile"
        user_profile.mkdir(parents=True, exist_ok=True)
        cmd = [
            "soffice",
            "--headless",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
            "--invisible",
            f"-env:UserInstallation=file://{user_profile}",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(tmp_dir),
            str(source_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603
        if completed.returncode != 0:
            raise RuntimeError(f"LibreOffice failed to create XLSX: {completed.stderr[:500]}")
        generated_path = tmp_dir / "input.xlsx"
        if not generated_path.exists():
            raise RuntimeError("LibreOffice did not generate the expected XLSX file.")
        shutil.copy(generated_path, path)


def create_ods(path: Path) -> None:
    """Creates a simple ODS file using LibreOffice conversion."""

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        source_path = tmp_dir / "input.xlsx"
        create_xlsx(source_path)
        user_profile = tmp_dir / "lo-profile"
        user_profile.mkdir(parents=True, exist_ok=True)
        cmd = [
            "soffice",
            "--headless",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
            "--invisible",
            f"-env:UserInstallation=file://{user_profile}",
            "--convert-to",
            "ods",
            "--outdir",
            str(tmp_dir),
            str(source_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603
        if completed.returncode != 0:
            raise RuntimeError(f"LibreOffice failed to create ODS: {completed.stderr[:500]}")
        generated_path = tmp_dir / "input.ods"
        if not generated_path.exists():
            raise RuntimeError("LibreOffice did not generate the expected ODS file.")
        shutil.copy(generated_path, path)


def create_jpg(path: Path) -> None:
    """Creates a simple JPG image.

    Args:
        path: The path to the file.
    """
    img = Image.new("RGB", (10, 10), color="red")
    img.save(path, "jpeg")


def create_png(path: Path) -> None:
    """Creates a simple PNG image.

    Args:
        path: The path to the file.
    """
    img = Image.new("RGB", (10, 10), color="green")
    img.save(path, "png")


def create_gif(path: Path) -> None:
    """Creates a simple GIF image.

    Args:
        path: The path to the file.
    """
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(path, "gif")


def create_bmp(path: Path) -> None:
    """Creates a simple BMP image.

    Args:
        path: The path to the file.
    """
    img = Image.new("RGB", (10, 10), color="yellow")
    img.save(path, "bmp")


def create_pdf(path: Path, content: str = "This is a valid PDF file.") -> None:
    """Creates a simple, valid PDF file.

    Args:
        path: The path to the file.
        content: The content of the file.
    """
    pdf_canvas = canvas.Canvas(str(path), pagesize=letter)
    pdf_canvas.drawString(100, 750, content)
    pdf_canvas.save()


def create_html(path: Path, content: str = "<h1>This is a test HTML file.</h1>") -> None:
    """Creates a simple HTML file.

    Args:
        path: The path to the file.
        content: The content of the file.
    """
    path.write_text(content)


def create_rtf(path: Path, content: str = "This is a test RTF file.") -> None:
    """Creates a simple RTF file.

    Args:
        path: The path to the file.
        content: The content of the file.
    """
    rtf_content = f"{{{{\rtf1\\ansi\\deff0 {{{{\fonttbl {{{{\f0 Arial;}}}}}}}}\\f0\\fs24 {content}}}}}"
    path.write_text(rtf_content)


def create_xlsb(path: Path) -> None:
    """Copies a valid XLSB file from the fixtures directory.

    Args:
        path: The path to the file.
    """
    fixture_path = Path(__file__).parent.parent / "fixtures" / "file_samples" / "valid_test.xlsb"
    shutil.copy(fixture_path, path)


def create_csv(path: Path, content: str = "col1,col2\nval1,val2") -> None:
    """Creates a simple CSV file.

    Args:
        path: The path to the file.
        content: The content of the file.
    """
    path.write_text(content)


def create_json(path: Path, content: str = """{"key": "value"}""") -> None:
    """Creates a simple JSON file.

    Args:
        path: The path to the file.
        content: The content of the file.
    """
    path.write_text(content)


def create_md(path: Path, content: str = "# Markdown") -> None:
    """Creates a simple Markdown file.

    Args:
        path: The path to the file.
        content: The content of the file.
    """
    path.write_text(content)


def create_xml(path: Path, content: str = "<root><test>value</test></root>") -> None:
    """Creates a simple XML file.

    Args:
        path: The path to the file.
        content: The content of the file.
    """
    path.write_text(content)


def create_media_from_fixture(path: Path, source_filename: str) -> None:
    """Copies a valid media file from the fixtures directory.

    Args:
        path: The path to the file.
        source_filename: The name of the source file.
    """
    fixture_path = Path(__file__).parent.parent / "fixtures" / "file_samples" / source_filename
    shutil.copy(fixture_path, path)


def create_pptx(path: Path) -> None:
    """Copies a valid PPTX file from the fixtures directory."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "file_samples" / "valid_test.pptx"
    shutil.copy(fixture_path, path)


def create_xlsm(path: Path) -> None:
    """Copies a valid XLSM file from the fixtures directory."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "file_samples" / "valid_test.xlsm"
    shutil.copy(fixture_path, path)


def create_docm(path: Path) -> None:
    """Copies a valid DOCM file from the fixtures directory."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "file_samples" / "valid_test.docm"
    shutil.copy(fixture_path, path)


def create_odg(path: Path) -> None:
    """Copies a valid ODG file from the fixtures directory."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "file_samples" / "valid_test.odg"
    shutil.copy(fixture_path, path)


def create_jfif(path: Path) -> None:
    """Creates a simple JFIF (JPEG) image."""
    img = Image.new("RGB", (10, 10), color="purple")
    img.save(path, "jpeg")


def create_log(path: Path, content: str = "This is a test log file.") -> None:
    """Creates a simple log file."""
    path.write_text(content)


def create_htm(path: Path, content: str = "<h1>This is a test HTM file.</h1>") -> None:
    """Creates a simple HTM file."""
    path.write_text(content)


def create_tif(path: Path) -> None:
    """Creates a simple TIF image."""
    img = Image.new("RGB", (10, 10), color="cyan")
    img.save(path, "tiff")


FILE_GENERATORS: dict[str, Callable[..., None]] = {
    ".txt": create_txt,
    ".pdf": create_pdf,
    ".doc": create_doc,
    ".docx": create_docx,
    ".odt": create_odt,
    ".xls": create_xls,
    ".xlsx": create_xlsx,
    ".xlsb": create_xlsb,
    ".ods": create_ods,
    ".jpg": create_jpg,
    ".jpeg": create_jpg,  # Use the same generator for jpg and jpeg
    ".png": create_png,
    ".gif": create_gif,
    ".bmp": create_bmp,
    ".html": create_html,
    ".rtf": create_rtf,
    ".csv": create_csv,
    ".json": create_json,
    ".md": create_md,
    ".mp4": lambda p: create_media_from_fixture(p, "valid_test.mp4"),
    ".mov": lambda p: create_media_from_fixture(p, "valid_test.mov"),
    ".avi": lambda p: create_media_from_fixture(p, "valid_test.avi"),
    ".mkv": lambda p: create_media_from_fixture(p, "valid_test.mkv"),
    ".mp3": lambda p: create_media_from_fixture(p, "valid_test.mp3"),
    ".wav": lambda p: create_media_from_fixture(p, "valid_test.wav"),
    ".flac": lambda p: create_media_from_fixture(p, "valid_test.flac"),
    ".ogg": lambda p: create_media_from_fixture(p, "valid_test.ogg"),
    ".xml": create_xml,
    ".pptx": create_pptx,
    ".xlsm": create_xlsm,
    ".docm": create_docm,
    ".log": create_log,
    ".htm": create_htm,
    ".jfif": create_jfif,
    ".odg": create_odg,
    ".tif": create_tif,
}

SUPPORTED_EXTENSIONS_PARAMS = sorted(set(AnalysisService._SUPPORTED_EXTENSIONS))


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS_PARAMS)
def test_file_extension_processing(
    db_session: Engine,
    e2e_pubsub: tuple[Any, Any],
    tmp_path: Path,
    extension: str,
    mock_pncp_server: MockPNCP,
    gcs_cleanup_manager: GcsCleanupManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Tests the full E2E processing for various file extensions by running the
    worker as a subprocess and using a mock PNCP server to provide the files.

    Args:
        db_session: The database session.
        e2e_pubsub: The pub/sub fixture.
        tmp_path: The temporary path fixture.
        extension: The file extension to test.
        mock_pncp_server: The mock PNCP server.
        gcs_cleanup_manager: The GCS cleanup manager.
    """
    expected_status = ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL

    publisher, topic_path = e2e_pubsub
    gcs_provider = GcsProvider()
    config = ConfigProvider.get_config()
    bucket_name = config.GCP_GCS_BUCKET_PROCUREMENTS
    gcs_client = gcs_provider.get_client()

    # 1. Generate file locally
    file_generator = FILE_GENERATORS[extension]
    file_name = f"test_document{extension}"
    local_file_path = tmp_path / file_name
    file_generator(local_file_path)
    assert local_file_path.exists()

    # 2. Configure mock PNCP server
    file_id = uuid.uuid4()
    procurement_control_number = f"file-ext-test-{uuid.uuid4().hex[:6]}"

    mock_pncp_server.file_content = local_file_path.read_bytes()
    mock_pncp_server.file_metadata = [  # type: ignore
        {
            "id": str(file_id),
            "url": f"{mock_pncp_server.url}/pncp-api/v1/contratacoes/{file_id}/arquivos/{file_name}",
            "titulo": file_name,
            "tipoDocumentoId": 2,
            "ativo": True,
            "sequencialDocumento": 1,
            "dataPublicacaoPncp": datetime.now().isoformat(),
            "cnpj": "00000000000191",
            "anoCompra": 2025,
            "sequencialCompra": 1,
            "statusAtivo": True,
            "tipoDocumentoNome": "Edital de Convocação",
            "tipoDocumentoDescricao": "Edital de Convocação",
        }
    ]
    monkeypatch.setenv("PNCP_INTEGRATION_API_URL", mock_pncp_server.url)

    # 3. Setup database records
    version_number = 1
    raw_data_json = json.dumps(
        {
            "anoCompra": 2025,
            "dataAtualizacao": "2025-08-23T14:30:00",
            "dataPublicacaoPncp": "2025-08-23T14:30:00",
            "sequencialCompra": 1,
            "numeroControlePNCP": procurement_control_number,
            "objetoCompra": f"Test for {extension}",
            "srp": False,
            "orgaoEntidade": {
                "cnpj": "00000000000191",
                "razaoSocial": "Test Org",
                "poderId": "E",
                "esferaId": "F",
            },
            "processo": "1/2025",
            "amparoLegal": {"codigo": 1, "nome": "Lei 14.133/2021", "descricao": "Art. 75, II"},
            "numeroCompra": "1/2025",
            "unidadeOrgao": {
                "codigoUnidade": "1",
                "nomeUnidade": "Test Unit",
                "ufNome": "SP",
                "ufSigla": "SP",
                "municipioNome": "SAO PAULO",
                "codigoIbge": "3550308",
            },
            "modalidadeId": 1,
            "dataAtualizacaoGlobal": "2025-08-23T14:30:00",
            "modoDisputaId": 1,
            "situacaoCompraId": 1,
            "usuarioNome": "Test",
        }
    )
    procurement_model = Procurement.model_validate(json.loads(raw_data_json))

    # 4. Run pre-analysis
    db_engine = db_session
    pubsub_provider = PubSubProvider()
    gcs_provider = GcsProvider()
    ai_provider = AiProvider(Analysis)
    http_provider = HttpProvider()

    analysis_repo = AnalysisRepository(engine=db_engine)
    source_document_repo = SourceDocumentsRepository(engine=db_engine)
    file_record_repo = FileRecordsRepository(engine=db_engine)
    procurement_repo = ProcurementsRepository(
        engine=db_engine, pubsub_provider=pubsub_provider, http_provider=http_provider
    )
    status_history_repo = StatusHistoryRepository(engine=db_engine)
    budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)

    service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        http_provider=http_provider,
        pubsub_provider=pubsub_provider,
        gcs_path_prefix=gcs_cleanup_manager.prefix,
    )

    # Mock the document processing to avoid actual HTTP calls
    service.procurement_repo.process_procurement_documents = lambda p: [
        ProcessedFile(
            source_document_id=str(file_id),
            raw_document_metadata=mock_pncp_server.file_metadata[0],
            relative_path=file_name,
            content=local_file_path.read_bytes(),
        )
    ]

    service._pre_analyze_procurement(procurement_model, json.loads(raw_data_json))

    # 5. Fetch the created analysis_id
    with db_session.connect() as connection:
        analysis_id = connection.execute(
            text(
                """SELECT analysis_id FROM procurement_analyses
                WHERE procurement_control_number = :pcn AND version_number = :vn"""
            ),
            {"pcn": procurement_control_number, "vn": version_number},
        ).scalar_one()

    # 6. Trigger worker by publishing a message
    message_data = {"analysis_id": str(analysis_id)}
    message_json = json.dumps(message_data)
    publisher.publish(topic_path, message_json.encode())
    print(f"Published message for analysis_id: {analysis_id}")

    # 7. Run the worker as a subprocess
    gcs_prefix = gcs_cleanup_manager.prefix
    worker_command = (
        f"poetry run pd worker start --max-messages 1 --timeout 15 "
        f"--gcs-path-prefix {gcs_prefix} --no-ai-tools --thinking-level LOW"
    )
    run_command(worker_command)

    # 8. Assertions
    with db_session.connect() as connection:
        final_status = connection.execute(
            text("SELECT status FROM procurement_analyses WHERE analysis_id = :analysis_id"),
            {"analysis_id": analysis_id},
        ).scalar_one_or_none()

        assert (
            final_status == expected_status.value
        ), f"Expected {expected_status.value} for {extension}, but got {final_status}"

        file_record = (
            connection.execute(
                text(
                    """
                    SELECT fr.*
                    FROM file_records fr
                    JOIN procurement_source_documents psd ON fr.source_document_id = psd.id
                    WHERE psd.analysis_id = :analysis_id AND fr.file_name = :file_name
                    """
                ),
                {"analysis_id": analysis_id, "file_name": file_name},
            )
            .mappings()
            .one()
        )

        assert (
            file_record["exclusion_reason"] is None
        ), f"File was unexpectedly excluded with reason: {file_record['exclusion_reason']}"
        assert file_record["included_in_analysis"] is True, "File was not included in analysis"

        assert gcs_client.bucket(bucket_name).blob(file_record["gcs_path"]).exists()
