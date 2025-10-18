import io
import tarfile
import zipfile
from datetime import date
from http import HTTPStatus
from typing import Any
from unittest.mock import MagicMock, patch

import py7zr
import pytest
import rarfile
import requests
from google.api_core import exceptions
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
def mock_http_provider() -> MagicMock:
    """Fixture for a mocked HttpProvider."""
    return MagicMock()


@pytest.fixture
def repo(
    mock_engine: MagicMock, mock_pubsub_provider: MagicMock, mock_http_provider: MagicMock
) -> ProcurementsRepository:
    """Provides a ProcurementsRepository instance with mocked dependencies."""
    with patch("public_detective.providers.config.ConfigProvider.get_config") as mock_get_config:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        return ProcurementsRepository(
            engine=mock_engine, pubsub_provider=mock_pubsub_provider, http_provider=mock_http_provider
        )


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


def test_extract_from_tar_empty_file(repo: ProcurementsRepository) -> None:
    """Tests that the tar extraction handles empty/unextractable files gracefully."""
    mock_archive = MagicMock()
    mock_member = MagicMock()
    mock_member.isfile.return_value = True
    mock_archive.getmembers.return_value = [mock_member]
    mock_archive.extractfile.return_value = None  # Simulate an unextractable file

    with patch("tarfile.open", return_value=mock_archive):
        result = repo._extract_from_tar(b"dummy tar content")
        assert result == []


def test_get_all_documents_metadata_success(repo: ProcurementsRepository) -> None:
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
    repo.http_provider.get.return_value = mock_response

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


def test_get_all_documents_metadata_all_active(repo: ProcurementsRepository) -> None:
    """Tests fetching document metadata when all documents are active."""
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
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [raw_doc1]
    repo.http_provider.get.return_value = mock_response

    procurement = MagicMock(spec=Procurement)
    procurement.government_entity = MagicMock()
    procurement.government_entity.cnpj = "123"
    procurement.procurement_year = "2025"
    procurement.procurement_sequence = "1"
    repo.config.PNCP_INTEGRATION_API_URL = "http://test.api/"

    docs = repo._get_all_documents_metadata(procurement)

    assert len(docs) == 1
    assert docs[0][1] == raw_doc1


def test_get_all_documents_metadata_request_error(repo: ProcurementsRepository) -> None:
    """Tests handling of request errors when fetching document metadata."""
    repo.http_provider.get.side_effect = requests.RequestException
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "123"
    procurement.government_entity = MagicMock()
    procurement.government_entity.cnpj = "123"
    procurement.procurement_year = 2025
    procurement.procurement_sequence = 1
    repo.config.PNCP_INTEGRATION_API_URL = "http://test.api/"
    docs = repo._get_all_documents_metadata(procurement)
    assert docs == []


def test_download_file_content_success(repo: ProcurementsRepository) -> None:
    """Tests successful download of file content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"file content"
    repo.http_provider.get.return_value = mock_response
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


@pytest.fixture
def mock_procurement() -> MagicMock:
    """Provides a detailed mock Procurement object for testing."""
    procurement = MagicMock(spec=Procurement)
    mock_entity = MagicMock()
    mock_entity.cnpj = "12345678000195"
    procurement.government_entity = mock_entity
    procurement.procurement_year = 2023
    procurement.procurement_sequence = 1
    procurement.pncp_control_number = "123"
    procurement.proposal_opening_date = date(2023, 1, 1)
    procurement.proposal_closing_date = date(2023, 1, 2)
    procurement.object_description = "Test Object"
    procurement.total_awarded_value = 1000.0
    procurement.is_srp = False
    procurement.pncp_publication_date = date(2023, 1, 1)
    procurement.last_update_date = date(2023, 1, 1)
    procurement.modality = 5
    procurement.procurement_status = 1
    procurement.total_estimated_value = 1200.0
    return procurement


def test_extract_from_rar_with_directory(repo: ProcurementsRepository) -> None:
    """Tests that directories inside a RAR archive are ignored."""
    mock_archive = MagicMock()
    mock_file_info = MagicMock()
    mock_file_info.filename = "file.txt"
    mock_file_info.isdir.return_value = False
    mock_dir_info = MagicMock()
    mock_dir_info.isdir.return_value = True

    mock_archive.infolist.return_value = [mock_dir_info, mock_file_info]
    mock_archive.read.return_value = b"content"

    # Configure the context manager correctly
    mock_rar_file_context = MagicMock()
    mock_rar_file_context.__enter__.return_value = mock_archive

    with patch("rarfile.RarFile", return_value=mock_rar_file_context):
        result = repo._extract_from_rar(b"dummy rar content")
        assert len(result) == 1
        assert result[0] == ("file.txt", b"content")
        mock_archive.read.assert_called_once_with("file.txt")


def test_extract_from_rar_with_bad_file(repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests that a BadRarFile error is handled gracefully."""
    with patch("rarfile.RarFile", side_effect=rarfile.BadRarFile):
        result = repo._extract_from_rar(b"bad content")
        assert result == []
        assert "Failed to extract from a corrupted or invalid RAR file" in caplog.text


def test_create_zip_from_files_empty(repo: ProcurementsRepository) -> None:
    """Tests that creating a zip from no files returns None."""
    assert repo.create_zip_from_files([], "123") is None


@patch("zipfile.ZipFile")
def test_create_zip_from_files_exception(mock_zipfile: MagicMock, repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests that an exception during zip creation is handled."""
    mock_zipfile.side_effect = Exception("Zip error")
    result = repo.create_zip_from_files([("test.txt", b"content")], "123")
    assert result is None
    assert "Failed to create final ZIP archive for 123: Zip error" in caplog.text


def test_get_all_documents_metadata_request_exception(
    repo: ProcurementsRepository, mock_procurement: MagicMock, caplog: Any
) -> None:
    """Tests handling of RequestException when fetching document metadata."""
    repo.http_provider.get.side_effect = requests.RequestException("Network error")
    repo.config.PNCP_INTEGRATION_API_URL = "http://dummy.url"
    result = repo._get_all_documents_metadata(mock_procurement)
    assert result == []
    assert "Failed to get/validate document list for 123: Network error" in caplog.text


def test_download_file_content_request_exception(repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests handling of RequestException during file download."""
    repo.http_provider.get.side_effect = requests.RequestException("Download failed")
    result = repo._download_file_content("http://example.com/file")
    assert result is None
    assert "Failed to download content from http://example.com/file: Download failed" in caplog.text


def test_get_all_documents_metadata_validation_error(
    repo: ProcurementsRepository, mock_procurement: MagicMock, caplog: Any
) -> None:
    """Tests handling of ValidationError when fetching document metadata."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = {"invalid": "data"}
    repo.http_provider.get.return_value = mock_response
    repo.config.PNCP_INTEGRATION_API_URL = "http://dummy.url"
    result = repo._get_all_documents_metadata(mock_procurement)
    assert result == []
    assert "Failed to get/validate document list for 123" in caplog.text


def test_determine_original_filename_request_exception(repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests handling of RequestException when determining filename."""
    repo.http_provider.head.side_effect = requests.RequestException("HEAD request failed")
    result = repo._determine_original_filename("http://example.com/file")
    assert result is None
    assert "Could not determine filename from headers for http://example.com/file" in caplog.text


def test_determine_original_filename_no_header(repo: ProcurementsRepository) -> None:
    """Tests handling of a missing Content-Disposition header."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.headers = {}  # No Content-Disposition header
    repo.http_provider.head.return_value = mock_response
    filename = repo._determine_original_filename("http://example.com/file")
    assert filename is None


def test_determine_original_filename_header_no_filename(repo: ProcurementsRepository) -> None:
    """Tests handling of a Content-Disposition header that is missing the filename."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.headers = {"Content-Disposition": "attachment"}
    repo.http_provider.head.return_value = mock_response
    filename = repo._determine_original_filename("http://example.com/file")
    assert filename is None


def test_determine_original_filename_success(repo: ProcurementsRepository) -> None:
    """Tests successful extraction of filename from Content-Disposition header."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.headers = {"Content-Disposition": 'attachment; filename="test_file.pdf"'}
    repo.http_provider.head.return_value = mock_response
    filename = repo._determine_original_filename("http://example.com/file")
    assert filename == "test_file.pdf"


def test_publish_procurement_to_pubsub_api_error(
    repo: ProcurementsRepository, mock_procurement: MagicMock, caplog: Any
) -> None:
    """Tests handling of GoogleAPICallError during pub/sub publish."""
    repo.pubsub_provider.publish.side_effect = exceptions.GoogleAPICallError("Pub/Sub error")
    mock_procurement.model_dump_json.return_value = "{}"

    result = repo.publish_procurement_to_pubsub(mock_procurement)
    assert result is False
    assert "Failed to publish message for 123: None Pub/Sub error" in caplog.text


def test_get_updated_procurements_request_exception(repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests handling of RequestException in get_updated_procurements."""
    repo.http_provider.get.side_effect = requests.exceptions.RequestException("API is down")
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)
    result = repo.get_updated_procurements(target_date)
    assert result == []
    assert "Error fetching updates on page 1: API is down" in caplog.text


def test_get_updated_procurements_validation_error(repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests handling of ValidationError in get_updated_procurements."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = {"invalid": "data"}
    repo.http_provider.get.return_value = mock_response
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)
    result = repo.get_updated_procurements(target_date)
    assert result == []
    assert "Data validation error on page 1" in caplog.text


def test_get_updated_procurements_with_raw_data_request_exception(repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests handling of RequestException in get_updated_procurements_with_raw_data."""
    repo.http_provider.get.side_effect = requests.exceptions.RequestException("API is down")
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)
    result = repo.get_updated_procurements_with_raw_data(target_date)
    assert result == []
    assert "Error fetching updates on page 1: API is down" in caplog.text


def test_get_updated_procurements_with_raw_data_validation_error(repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests handling of ValidationError in get_updated_procurements_with_raw_data."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = {"invalid": "data"}
    repo.http_provider.get.return_value = mock_response
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)
    result = repo.get_updated_procurements_with_raw_data(target_date)
    assert result == []
    assert "Data validation error on page 1" in caplog.text


def test_get_updated_procurements_with_raw_data_no_content(repo: ProcurementsRepository) -> None:
    """Tests get_updated_procurements_with_raw_data with a 204 No Content response."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.NO_CONTENT
    repo.http_provider.get.return_value = mock_response
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)
    result = repo.get_updated_procurements_with_raw_data(target_date)
    assert result == []


def test_get_updated_procurements_with_raw_data_happy_path(repo: ProcurementsRepository) -> None:
    """Tests the happy path for get_updated_procurements_with_raw_data."""
    raw_procurement_data = _get_mock_procurement_data("PNCP-456")
    mock_response_with_data = MagicMock()
    mock_response_with_data.status_code = HTTPStatus.OK
    mock_response_with_data.json.return_value = {
        "totalRegistros": 1,
        "numeroPagina": 1,
        "totalPaginas": 1,
        "data": [raw_procurement_data],
    }

    mock_response_no_content = MagicMock()
    mock_response_no_content.status_code = HTTPStatus.NO_CONTENT

    # Simulate finding data for the first modality, then no data for the rest
    repo.http_provider.get.side_effect = [mock_response_with_data] + [mock_response_no_content] * 3

    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)

    result = repo.get_updated_procurements_with_raw_data(target_date)

    assert len(result) == 1
    procurement_model, raw_data = result[0]
    assert isinstance(procurement_model, Procurement)
    assert procurement_model.pncp_control_number == "PNCP-456"
    assert raw_data == raw_procurement_data


def test_get_updated_procurements_with_raw_data_pagination(repo: ProcurementsRepository) -> None:
    """Tests that the raw data procurement fetching logic correctly handles pagination."""
    raw_proc_page1 = _get_mock_procurement_data("PNCP-RAW-PAGE-1")
    raw_proc_page2 = _get_mock_procurement_data("PNCP-RAW-PAGE-2")

    mock_response_p1 = MagicMock()
    mock_response_p1.status_code = HTTPStatus.OK
    mock_response_p1.json.return_value = {
        "totalRegistros": 2,
        "numeroPagina": 1,
        "totalPaginas": 2,
        "data": [raw_proc_page1],
    }

    mock_response_p2 = MagicMock()
    mock_response_p2.status_code = HTTPStatus.OK
    mock_response_p2.json.return_value = {
        "totalRegistros": 2,
        "numeroPagina": 2,
        "totalPaginas": 2,
        "data": [raw_proc_page2],
    }

    repo.http_provider.get.side_effect = [mock_response_p1, mock_response_p2] + [
        MagicMock(status_code=HTTPStatus.NO_CONTENT)
    ] * 3
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = ["12345"]
    target_date = date(2023, 1, 1)

    result = repo.get_updated_procurements_with_raw_data(target_date)

    assert len(result) == 2
    assert result[0][0].pncp_control_number == "PNCP-RAW-PAGE-1"
    assert result[1][0].pncp_control_number == "PNCP-RAW-PAGE-2"
    assert result[0][1] == raw_proc_page1
    assert result[1][1] == raw_proc_page2


@patch.object(ProcurementsRepository, "_extract_from_zip", side_effect=Exception("ZIP processing error"))
def test_recursive_file_processing_generic_archive_exception(
    mock_extract: MagicMock, repo: ProcurementsRepository, caplog: Any
) -> None:
    """Tests that an exception during archive extraction is handled and the file is treated as a single entity."""
    file_collection: list[Any] = []
    repo._recursive_file_processing(
        source_document_id="doc1",
        content=b"zip_content",
        current_path="archive.zip",
        nesting_level=0,
        file_collection=file_collection,
        raw_document_metadata={},
    )
    assert len(file_collection) == 1
    assert file_collection[0].relative_path == "archive.zip"
    assert file_collection[0].content == b"zip_content"
    assert "Could not process archive 'archive.zip': ZIP processing error" in caplog.text


def test_get_procurement_by_hash_found(repo: ProcurementsRepository) -> None:
    """Tests checking a hash that exists."""
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = 1
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_scalar
    assert repo.get_procurement_by_hash("existing_hash") is True


def test_get_procurement_by_hash_not_found(repo: ProcurementsRepository) -> None:
    """Tests checking a hash that does not exist."""
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = None
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_scalar
    assert repo.get_procurement_by_hash("new_hash") is False


def test_get_procurement_by_id_and_version_found(repo: ProcurementsRepository) -> None:
    """Tests fetching a procurement that exists."""
    raw_data = _get_mock_procurement_data("PNCP-123")
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = raw_data
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_scalar
    result = repo.get_procurement_by_id_and_version("PNCP-123", 1)
    assert result is not None
    assert isinstance(result, Procurement)
    assert result.pncp_control_number == "PNCP-123"


def test_get_procurement_by_id_and_version_not_found(repo: ProcurementsRepository) -> None:
    """Tests fetching a procurement that does not exist."""
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = None
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_scalar
    result = repo.get_procurement_by_id_and_version("123", 1)
    assert result is None


def test_get_procurement_uuid_not_found(repo: ProcurementsRepository) -> None:
    """Tests fetching a procurement UUID that does not exist."""
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = None
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_scalar
    result = repo.get_procurement_uuid("non_existent", 1)
    assert result is None


def test_get_procurement_uuid_found(repo: ProcurementsRepository) -> None:
    """Tests fetching a procurement UUID that exists."""
    from uuid import uuid4

    mock_uuid = uuid4()
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = mock_uuid
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_scalar
    result = repo.get_procurement_uuid("123", 1)
    assert result == mock_uuid


def test_save_procurement_version(repo: ProcurementsRepository, mock_procurement: MagicMock) -> None:
    """Tests saving a new procurement version."""
    repo.save_procurement_version(mock_procurement, '{"key":"value"}', 1, "hash123")
    assert repo.engine.connect.return_value.__enter__.return_value.execute.call_count == 1
    assert repo.engine.connect.return_value.__enter__.return_value.commit.call_count == 1


def test_get_updated_procurements_happy_path(repo: ProcurementsRepository) -> None:
    """Tests the happy path for get_updated_procurements."""
    mock_response_with_data = MagicMock()
    mock_response_with_data.status_code = HTTPStatus.OK
    mock_response_with_data.json.return_value = {
        "totalRegistros": 1,
        "numeroPagina": 1,
        "totalPaginas": 1,
        "data": [
            {
                "cnpj": "12345678000195",
                "anoCompra": 2023,
                "sequencialCompra": 1,
                "dataAtualizacao": "2023-01-01T12:00:00",
                "dataPublicacaoPncp": "2023-01-01T12:00:00",
                "situacaoCompraId": 1,
                "modalidadeId": 5,
                "objetoCompra": "Test Object",
                "numeroCompra": "001/2023",
                "valorTotalEstimado": 100.0,
                "valorTotalHomologado": 100.0,
                "dataAberturaProposta": "2023-01-01T12:00:00",
                "dataEncerramentoProposta": "2023-01-02T12:00:00",
                "srp": False,
                "orgaoEntidade": {
                    "cnpj": "12345678000195",
                    "razaoSocial": "Test Org",
                    "poderId": "E",
                    "esferaId": "F",
                },
                "unidadeOrgao": {
                    "cnpj": "12345678000195",
                    "nomeUnidade": "Test Unit",
                    "ufNome": "TEST",
                    "codigoUnidade": "1",
                    "ufSigla": "TT",
                    "municipioNome": "Test City",
                    "codigoIbge": "123",
                },
                "processo": "123/2023",
                "amparoLegal": {"codigo": 1, "nome": "Law 123", "descricao": "Legal Support Desc"},
                "numeroControlePNCP": "PNCP-123",
                "dataAtualizacaoGlobal": "2023-01-01T12:00:00",
                "modoDisputaId": 1,
                "usuarioNome": "Test User",
            }
        ],
    }

    mock_response_no_content = MagicMock()
    mock_response_no_content.status_code = HTTPStatus.NO_CONTENT

    repo.http_provider.get.side_effect = [mock_response_with_data] + [mock_response_no_content] * 10
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)
    result = repo.get_updated_procurements(target_date)
    assert len(result) == 1
    assert result[0].pncp_control_number == "PNCP-123"


def test_get_updated_procurements_no_content(repo: ProcurementsRepository) -> None:
    """Tests get_updated_procurements with a 204 No Content response."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.NO_CONTENT
    repo.http_provider.get.return_value = mock_response

    target_date = date(2023, 1, 1)
    result = repo.get_updated_procurements(target_date)
    assert result == []


def test_get_latest_version_found(repo: ProcurementsRepository) -> None:
    """Tests retrieving the latest version number when one exists."""
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = 5
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_scalar
    result = repo.get_latest_version("some_pncp_number")
    assert result == 5


def test_get_latest_version_not_found(repo: ProcurementsRepository) -> None:
    """Tests retrieving the latest version when none exists, expecting 0."""
    mock_scalar = MagicMock()
    mock_scalar.scalar_one_or_none.return_value = None
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value = mock_scalar
    result = repo.get_latest_version("some_pncp_number")
    assert result == 0


def test_get_updated_procurements_pagination(repo: ProcurementsRepository) -> None:
    """Tests that the procurement fetching logic correctly handles pagination."""
    raw_proc_page1 = _get_mock_procurement_data("PNCP-PAGE-1")
    raw_proc_page2 = _get_mock_procurement_data("PNCP-PAGE-2")

    # Response for page 1
    mock_response_p1 = MagicMock()
    mock_response_p1.status_code = HTTPStatus.OK
    mock_response_p1.json.return_value = {
        "totalRegistros": 2,
        "numeroPagina": 1,
        "totalPaginas": 2,
        "data": [raw_proc_page1],
    }

    # Response for page 2
    mock_response_p2 = MagicMock()
    mock_response_p2.status_code = HTTPStatus.OK
    mock_response_p2.json.return_value = {
        "totalRegistros": 2,
        "numeroPagina": 2,
        "totalPaginas": 2,
        "data": [raw_proc_page2],
    }

    repo.http_provider.get.side_effect = [mock_response_p1, mock_response_p2] + [
        MagicMock(status_code=HTTPStatus.NO_CONTENT)
    ] * 3

    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = ["12345"]  # Use a specific code to limit loops
    target_date = date(2023, 1, 1)

    result = repo.get_updated_procurements(target_date)

    assert len(result) == 2
    assert result[0].pncp_control_number == "PNCP-PAGE-1"
    assert result[1].pncp_control_number == "PNCP-PAGE-2"
    # Ensure it called the API for both pages for the first modality
    assert repo.http_provider.get.call_count >= 2


def test_get_updated_procurements_happy_path_multiple_modalities(repo: ProcurementsRepository) -> None:
    """Tests the happy path for get_updated_procurements across multiple modalities."""
    raw_procurement_data = _get_mock_procurement_data("PNCP-789")
    mock_response_with_data = MagicMock()
    mock_response_with_data.status_code = HTTPStatus.OK
    mock_response_with_data.json.return_value = {
        "totalRegistros": 1,
        "numeroPagina": 1,
        "totalPaginas": 1,
        "data": [raw_procurement_data],
    }

    mock_response_no_content = MagicMock()
    mock_response_no_content.status_code = HTTPStatus.NO_CONTENT

    # Simulate finding data for the first modality, then no data for the rest
    repo.http_provider.get.side_effect = [mock_response_with_data] + [mock_response_no_content] * 3

    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)

    result = repo.get_updated_procurements(target_date)

    assert len(result) == 1
    assert result[0].pncp_control_number == "PNCP-789"
