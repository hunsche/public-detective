import io
import tarfile
import zipfile
from unittest.mock import MagicMock, patch

import py7zr
import pytest
import requests
from public_detective.models.procurements import Procurement, ProcurementDocument
from public_detective.repositories.procurements import ProcessedFile, ProcurementsRepository


def _get_mock_procurement_data(control_number: str) -> dict:
    """Returns a dictionary with minimal valid data for a Procurement model."""
    return {
        "processo": "123",
        "objetoCompra": "Test Object",
        "amparoLegal": {"codigo": 1, "nome": "Test Law", "descricao": "Desc"},
        "srp": False,
        "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Test Org", "poderId": "E", "esferaId": "F"},
        "anoCompra": 2025,
        "sequencialCompra": 1,
        "dataPublicacaoPncp": "2025-01-01T12:00:00",
        "dataAtualizacao": "2025-01-01T12:00:00",
        "numeroCompra": "1/2025",
        "unidadeOrgao": {
            "ufNome": "Test State",
            "codigoUnidade": "123",
            "nomeUnidade": "Test Unit",
            "ufSigla": "TS",
            "municipioNome": "Test City",
            "codigoIbge": "12345",
        },
        "modalidadeId": 1,
        "numeroControlePNCP": control_number,
        "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
        "modoDisputaId": 1,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
    }


@pytest.fixture
def mock_engine() -> MagicMock:
    """Fixture for a mocked database engine."""
    return MagicMock()


@pytest.fixture
def mock_pubsub_provider() -> MagicMock:
    """Fixture for a mocked PubSubProvider."""
    return MagicMock()


@pytest.fixture
def repo(mock_engine: MagicMock, mock_pubsub_provider: MagicMock) -> ProcurementsRepository:
    """Provides a ProcurementsRepository instance with mocked dependencies."""
    with patch("public_detective.providers.config.ConfigProvider.get_config") as mock_get_config:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        return ProcurementsRepository(engine=mock_engine, pubsub_provider=mock_pubsub_provider)


def test_extract_from_zip(repo: ProcurementsRepository) -> None:
    """Tests extracting files from a ZIP archive."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("file1.txt", "content1")
        zf.writestr("file2.txt", "content2")
    zip_content = zip_buffer.getvalue()
    extracted_files = repo._extract_from_zip(zip_content)
    assert len(extracted_files) == 2
    assert ("file1.txt", b"content1") in extracted_files
    assert ("file2.txt", b"content2") in extracted_files


def test_extract_from_7z(repo: ProcurementsRepository) -> None:
    """Tests extracting files from a 7z archive."""
    s_buffer = io.BytesIO()
    with py7zr.SevenZipFile(s_buffer, "w") as archive:
        archive.writestr("content1", "file1.txt")
        archive.writestr("content2", "file2.txt")
    s_content = s_buffer.getvalue()
    extracted_files = repo._extract_from_7z(s_content)
    assert len(extracted_files) == 2
    assert ("file1.txt", b"content1") in extracted_files
    assert ("file2.txt", b"content2") in extracted_files


def test_extract_from_tar(repo: ProcurementsRepository) -> None:
    """Tests extracting files from a TAR archive."""
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        info1 = tarfile.TarInfo(name="file1.txt")
        info1.size = len(b"content1")
        tar.addfile(info1, io.BytesIO(b"content1"))
        info2 = tarfile.TarInfo(name="file2.txt")
        info2.size = len(b"content2")
        tar.addfile(info2, io.BytesIO(b"content2"))
    tar_content = tar_buffer.getvalue()
    extracted_files = repo._extract_from_tar(tar_content)
    assert len(extracted_files) == 2
    assert ("file1.txt", b"content1") in extracted_files
    assert ("file2.txt", b"content2") in extracted_files


@patch("requests.get")
def test_get_all_documents_metadata_success(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests successful fetching and filtering of document metadata."""
    raw_doc1 = {
        "sequencialDocumento": 1,
        "dataPublicacaoPncp": "2025-01-01T12:00:00",
        "cnpj": "12345678000199",
        "anoCompra": 2025,
        "sequencialCompra": 1,
        "statusAtivo": True,
        "titulo": "doc1",
        "tipoDocumentoId": 1,
        "tipoDocumentoNome": "Edital",
        "tipoDocumentoDescricao": "Edital",
        "url": "http://example.com/doc1",
    }
    raw_doc2 = {
        "sequencialDocumento": 2,
        "dataPublicacaoPncp": "2025-01-01T12:00:00",
        "cnpj": "12345678000199",
        "anoCompra": 2025,
        "sequencialCompra": 1,
        "statusAtivo": False,
        "titulo": "doc2",
        "tipoDocumentoId": 2,
        "tipoDocumentoNome": "Outros",
        "tipoDocumentoDescricao": "Outros",
        "url": "http://example.com/doc2",
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [raw_doc1, raw_doc2]
    mock_get.return_value = mock_response

    procurement = MagicMock(spec=Procurement)
    procurement.government_entity = MagicMock()
    procurement.government_entity.cnpj = "123"
    procurement.procurement_year = "2025"
    procurement.procurement_sequence = "1"
    repo.config.PNCP_INTEGRATION_API_URL = "http://test.api/"

    docs = repo._get_all_documents_metadata(procurement)

    assert len(docs) == 1
    doc_model, raw_meta = docs[0]
    assert isinstance(doc_model, ProcurementDocument)
    assert doc_model.document_sequence == 1
    assert raw_meta == raw_doc1


@patch("requests.get")
def test_get_all_documents_metadata_request_error(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests handling of request errors when fetching document metadata."""
    mock_get.side_effect = requests.RequestException
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "123"
    procurement.government_entity = MagicMock()
    procurement.government_entity.cnpj = "123"
    procurement.procurement_year = 2025
    procurement.procurement_sequence = 1
    repo.config.PNCP_INTEGRATION_API_URL = "http://test.api/"
    docs = repo._get_all_documents_metadata(procurement)
    assert docs == []


@patch("requests.get")
def test_download_file_content_success(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests successful download of file content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"file content"
    mock_get.return_value = mock_response
    content = repo._download_file_content("http://test.url/file.pdf")
    assert content == b"file content"


def test_recursive_file_processing_non_archive(repo: ProcurementsRepository) -> None:
    """Tests that non-archive files are added directly to the collection."""
    file_collection: list[ProcessedFile] = []
    repo._recursive_file_processing(
        source_document_id="src-doc-1",
        content=b"simple content",
        current_path="file.txt",
        nesting_level=0,
        file_collection=file_collection,
        raw_document_metadata={"key": "value"},
    )
    assert len(file_collection) == 1
    processed_file = file_collection[0]
    assert processed_file.relative_path == "file.txt"
    assert processed_file.content == b"simple content"
    assert processed_file.raw_document_metadata == {"key": "value"}


def test_process_procurement_documents_download_fails(repo: ProcurementsRepository) -> None:
    """Tests that processing continues even if a document download fails."""
    procurement = MagicMock(spec=Procurement)
    mock_doc = (MagicMock(spec=ProcurementDocument), {"key": "value"})
    mock_doc[0].url = "http://fail.com"
    with patch.object(repo, "_get_all_documents_metadata", return_value=[mock_doc]):
        with patch.object(repo, "_download_file_content", return_value=None):
            result = repo.process_procurement_documents(procurement)
            assert result == []


def test_recursive_file_processing_corrupted_archive(repo: ProcurementsRepository) -> None:
    """Tests that a corrupted archive is treated as a single file."""
    file_collection: list[ProcessedFile] = []
    corrupted_content = b"not a zip"
    with patch.object(repo, "_extract_from_zip", side_effect=zipfile.BadZipFile):
        repo._recursive_file_processing(
            source_document_id="src-doc-1",
            content=corrupted_content,
            current_path="archive.zip",
            nesting_level=0,
            file_collection=file_collection,
            raw_document_metadata={"key": "value"},
        )
        assert len(file_collection) == 1
        assert file_collection[0].content == corrupted_content


def test_recursive_file_processing_7z(repo: ProcurementsRepository) -> None:
    """Tests that .7z files are dispatched to the correct handler."""
    with patch.object(repo, "_extract_from_7z") as mock_extract:
        repo._recursive_file_processing(
            source_document_id="src-doc-1",
            content=b"dummy",
            current_path="test.7z",
            nesting_level=0,
            file_collection=[],
            raw_document_metadata={},
        )
        mock_extract.assert_called_once()


def test_recursive_file_processing_tar(repo: ProcurementsRepository) -> None:
    """Tests that .tar files are dispatched to the correct handler."""
    with patch("tarfile.is_tarfile", return_value=True):
        with patch.object(repo, "_extract_from_tar") as mock_extract:
            repo._recursive_file_processing(
                source_document_id="src-doc-1",
                content=b"dummy",
                current_path="test.tar",
                nesting_level=0,
                file_collection=[],
                raw_document_metadata={},
            )
            mock_extract.assert_called_once()
