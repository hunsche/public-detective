import io
import tarfile
import zipfile
from datetime import date
from unittest.mock import MagicMock, patch

import py7zr
import pytest
import requests
from google.api_core import exceptions
from models.procurement import Procurement, ProcurementDocument
from repositories.procurement import ProcurementRepository


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
def mock_engine():
    """Fixture for a mocked database engine."""
    return MagicMock()


@pytest.fixture
def mock_pubsub_provider():
    """Fixture for a mocked PubSubProvider."""
    return MagicMock()


@pytest.fixture
def repo(mock_engine, mock_pubsub_provider):
    """Provides a ProcurementRepository instance with mocked dependencies."""
    with patch("providers.config.ConfigProvider.get_config") as mock_get_config:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        return ProcurementRepository(engine=mock_engine, pubsub_provider=mock_pubsub_provider)


def test_extract_from_zip(repo):
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


def test_extract_from_7z(repo):
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


def test_extract_from_tar(repo):
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
def test_get_all_documents_metadata_success(mock_get, repo):
    """Tests successful fetching and filtering of document metadata."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
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
        },
        {
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
        },
    ]
    mock_get.return_value = mock_response

    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "PNCP-123"
    procurement.government_entity = MagicMock()
    procurement.government_entity.cnpj = "123"
    procurement.procurement_year = "2025"
    procurement.procurement_sequence = "1"
    repo.config.PNCP_INTEGRATION_API_URL = "http://test.api/"

    docs = repo._get_all_documents_metadata(procurement)

    assert len(docs) == 1
    assert docs[0].document_sequence == 1


@patch("requests.get")
def test_get_all_documents_metadata_request_error(mock_get, repo):
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
def test_get_all_documents_metadata_empty_list(mock_get, repo):
    """Tests handling of an empty list of documents from the API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []
    mock_get.return_value = mock_response
    procurement = MagicMock(spec=Procurement)
    procurement.government_entity = MagicMock()
    procurement.government_entity.cnpj = "123"
    procurement.procurement_year = "2025"
    procurement.procurement_sequence = "1"
    repo.config.PNCP_INTEGRATION_API_URL = "http://test.api/"
    docs = repo._get_all_documents_metadata(procurement)
    assert docs == []


@patch("requests.get")
def test_download_file_content_success(mock_get, repo):
    """Tests successful download of file content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"file content"
    mock_get.return_value = mock_response

    content = repo._download_file_content("http://test.url/file.pdf")

    assert content == b"file content"
    mock_get.assert_called_once_with("http://test.url/file.pdf", timeout=90)


@patch("requests.get")
def test_download_file_content_error(mock_get, repo):
    """Tests handling of request errors during file download."""
    mock_get.side_effect = requests.RequestException

    content = repo._download_file_content("http://test.url/file.pdf")

    assert content is None


@patch("requests.head")
def test_determine_original_filename_success(mock_head, repo):
    """Tests successful determination of filename from Content-Disposition header."""
    mock_response = MagicMock()
    mock_response.headers = {"Content-Disposition": 'attachment; filename="test_file.pdf"'}
    mock_head.return_value = mock_response

    filename = repo._determine_original_filename("http://test.url/download")

    assert filename == "test_file.pdf"


@patch("requests.head")
def test_determine_original_filename_error(mock_head, repo):
    """Tests handling of request errors when determining filename."""
    mock_head.side_effect = requests.RequestException
    filename = repo._determine_original_filename("http://test")
    assert filename is None


@patch("requests.head")
def test_determine_original_filename_no_header(mock_head, repo):
    """Tests handling of missing Content-Disposition header."""
    mock_response = MagicMock()
    mock_response.headers = {}
    mock_head.return_value = mock_response
    filename = repo._determine_original_filename("http://test")
    assert filename is None


def test_create_zip_from_files_success(repo):
    """Tests successful creation of a ZIP archive from a list of files."""
    files = [("file1.txt", b"content1"), ("path/to/file2.txt", b"content2")]

    zip_bytes = repo.create_zip_from_files(files, "control-123")

    assert zip_bytes is not None
    zip_buffer = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        assert "file1.txt" in zf.namelist()
        assert "path_to_file2.txt" in zf.namelist()
        assert zf.read("file1.txt") == b"content1"
        assert zf.read("path_to_file2.txt") == b"content2"


def test_create_zip_from_files_empty_list(repo):
    """Tests that no ZIP is created if the file list is empty."""
    zip_bytes = repo.create_zip_from_files([], "control-123")
    assert zip_bytes is None


def test_publish_procurement_to_pubsub_error(repo, mock_pubsub_provider):
    """Tests handling of Google API errors when publishing to Pub/Sub."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "123"
    procurement.model_dump_json.return_value = '{"key": "value"}'
    mock_pubsub_provider.publish.side_effect = exceptions.GoogleAPICallError("test error")

    result = repo.publish_procurement_to_pubsub(procurement)

    assert result is False


def test_publish_procurement_to_pubsub_success(repo, mock_pubsub_provider):
    """Tests successful publishing of a procurement to Pub/Sub."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "123"
    procurement.model_dump_json.return_value = '{"key": "value"}'
    mock_pubsub_provider.publish.return_value = "message-id-123"

    result = repo.publish_procurement_to_pubsub(procurement)

    assert result is True
    mock_pubsub_provider.publish.assert_called_once()


def test_save_procurement(repo, mock_engine):
    """Tests saving a procurement to the database."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "PNCP-123"
    procurement.proposal_opening_date = "2025-01-01"
    procurement.proposal_closing_date = "2025-01-10"
    procurement.object_description = "Test Object"
    procurement.total_awarded_value = 1000.50
    procurement.is_srp = True
    procurement.procurement_year = 2025
    procurement.procurement_sequence = 1
    procurement.pncp_publication_date = "2025-01-01"
    procurement.last_update_date = "2025-01-02"
    procurement.modality = 1
    procurement.procurement_status = 1
    procurement.total_estimated_value = 1200.00

    repo.save_procurement(procurement)

    mock_engine.connect.assert_called_once()
    conn_mock = mock_engine.connect().__enter__()
    conn_mock.execute.assert_called_once()
    conn_mock.commit.assert_called_once()


def test_recursive_file_processing_non_archive(repo):
    """Tests that non-archive files are added directly to the collection."""
    file_collection = []
    repo._recursive_file_processing(b"simple content", "file.txt", 0, file_collection)
    assert file_collection == [("file.txt", b"simple content")]


@patch("requests.get")
def test_get_updated_procurements_pagination_and_error_handling(mock_get, repo):
    """Tests pagination and error handling in get_updated_procurements."""
    mock_response_page1 = MagicMock()
    mock_response_page1.status_code = 200
    mock_response_page1.json.return_value = {
        "data": [_get_mock_procurement_data("1")],
        "totalPaginas": 2,
        "numeroPagina": 1,
        "totalRegistros": 2,
    }

    mock_response_page2 = MagicMock()
    mock_response_page2.status_code = 200
    mock_response_page2.json.return_value = {
        "data": [_get_mock_procurement_data("2")],
        "totalPaginas": 2,
        "numeroPagina": 2,
        "totalRegistros": 2,
    }

    mock_response_no_content = MagicMock()
    mock_response_no_content.status_code = 204

    mock_response_val_error = MagicMock()
    mock_response_val_error.status_code = 200
    mock_response_val_error.json.return_value = {"data": [{"invalid_field": "1"}]}

    mock_get.side_effect = [
        mock_response_page1,
        mock_response_page2,
        mock_response_no_content,
        requests.exceptions.RequestException("Request failed"),
        mock_response_val_error,
    ]

    target_date = date(2025, 1, 1)
    repo.config.TARGET_IBGE_CODES = ["12345"]
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    procurements = repo.get_updated_procurements(target_date)

    assert len(procurements) == 2
    assert procurements[0].pncp_control_number == "1"
    assert procurements[1].pncp_control_number == "2"
    assert mock_get.call_count == 5


@patch("requests.get")
def test_get_updated_procurements_no_city_codes(mock_get, repo):
    """Tests that a nationwide search is performed if no city codes are configured."""
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_get.return_value = mock_response

    target_date = date(2025, 1, 1)
    repo.config.TARGET_IBGE_CODES = []
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    repo.get_updated_procurements(target_date)

    assert mock_get.call_count == 4
