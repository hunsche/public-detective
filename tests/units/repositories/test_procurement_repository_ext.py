import io
import re
import tarfile
import zipfile
from datetime import date
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import py7zr
import pytest
import rarfile
import requests
from google.api_core import exceptions
from public_detective.models.procurements import Procurement, ProcurementListResponse
from public_detective.repositories.procurements import ProcurementsRepository
from pydantic import ValidationError


@pytest.fixture
def mock_engine():
    """Provides a mock SQLAlchemy engine."""
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


@pytest.fixture
def mock_pubsub_provider():
    """Provides a mock PubSubProvider."""
    return MagicMock()


@pytest.fixture
def repository(mock_engine, mock_pubsub_provider):
    """Provides a ProcurementsRepository instance with mocked dependencies."""
    return ProcurementsRepository(engine=mock_engine, pubsub_provider=mock_pubsub_provider)


@pytest.fixture
def mock_procurement():
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


def test_extract_from_rar_with_bad_file(repository, caplog):
    """Tests that a BadRarFile error is handled gracefully."""
    with patch("rarfile.RarFile", side_effect=rarfile.BadRarFile):
        result = repository._extract_from_rar(b"bad content")
        assert result == []
        assert "Failed to extract from a corrupted or invalid RAR file" in caplog.text


def test_extract_from_7z(repository):
    """Tests successful extraction from a 7z archive."""
    zip_buffer = io.BytesIO()
    with py7zr.SevenZipFile(zip_buffer, "w") as z:
        z.writestr(b"hello", "test.txt")

    result = repository._extract_from_7z(zip_buffer.getvalue())
    assert len(result) == 1
    assert result[0][0] == "test.txt"
    assert result[0][1] == b"hello"


def test_extract_from_tar(repository):
    """Tests successful extraction from a TAR archive."""
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        data = b"hello"
        info = tarfile.TarInfo(name="test.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    result = repository._extract_from_tar(tar_buffer.getvalue())
    assert len(result) == 1
    assert result[0][0] == "test.txt"
    assert result[0][1] == b"hello"


def test_create_zip_from_files_empty(repository):
    """Tests that creating a zip from no files returns None."""
    assert repository.create_zip_from_files([], "123") is None


@patch("zipfile.ZipFile")
def test_create_zip_from_files_exception(mock_zipfile, repository, caplog):
    """Tests that an exception during zip creation is handled."""
    mock_zipfile.side_effect = Exception("Zip error")
    result = repository.create_zip_from_files([("test.txt", b"content")], "123")
    assert result is None
    assert "Failed to create final ZIP archive for 123: Zip error" in caplog.text


@patch("requests.get")
def test_get_all_documents_metadata_request_exception(mock_get, repository, mock_procurement, caplog):
    """Tests handling of RequestException when fetching document metadata."""
    mock_get.side_effect = requests.RequestException("Network error")
    result = repository._get_all_documents_metadata(mock_procurement)
    assert result == []
    assert "Failed to get/validate document list for 123: Network error" in caplog.text


@patch("requests.get")
def test_get_all_documents_metadata_validation_error(mock_get, repository, mock_procurement, caplog):
    """Tests handling of ValidationError when fetching document metadata."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = {"invalid": "data"}
    mock_get.return_value = mock_response

    result = repository._get_all_documents_metadata(mock_procurement)
    assert result == []
    assert "Failed to get/validate document list for 123" in caplog.text


@patch("requests.get")
def test_download_file_content_request_exception(mock_get, repository, caplog):
    """Tests handling of RequestException during file download."""
    mock_get.side_effect = requests.RequestException("Download failed")
    result = repository._download_file_content("http://example.com/file")
    assert result is None
    assert "Failed to download content from http://example.com/file: Download failed" in caplog.text


@patch("requests.head")
def test_determine_original_filename_request_exception(mock_head, repository, caplog):
    """Tests handling of RequestException when determining filename."""
    mock_head.side_effect = requests.RequestException("HEAD request failed")
    result = repository._determine_original_filename("http://example.com/file")
    assert result is None
    assert "Could not determine filename from headers for http://example.com/file" in caplog.text


@patch("requests.get")
def test_get_updated_procurements_request_exception(mock_get, repository, caplog):
    """Tests handling of RequestException in get_updated_procurements."""
    mock_get.side_effect = requests.exceptions.RequestException("API is down")
    target_date = date(2023, 1, 1)
    result = repository.get_updated_procurements(target_date)
    assert result == []
    assert "Error fetching updates on page 1: API is down" in caplog.text


@patch("requests.get")
def test_get_updated_procurements_validation_error(mock_get, repository, caplog):
    """Tests handling of ValidationError in get_updated_procurements."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = {"invalid": "data"}
    mock_get.return_value = mock_response

    target_date = date(2023, 1, 1)
    result = repository.get_updated_procurements(target_date)
    assert result == []
    assert "Data validation error on page 1" in caplog.text


@patch("requests.get")
def test_get_updated_procurements_with_raw_data_request_exception(mock_get, repository, caplog):
    """Tests handling of RequestException in get_updated_procurements_with_raw_data."""
    mock_get.side_effect = requests.exceptions.RequestException("API is down")
    target_date = date(2023, 1, 1)
    result = repository.get_updated_procurements_with_raw_data(target_date)
    assert result == []
    assert "Error fetching updates on page 1: API is down" in caplog.text


@patch("requests.get")
def test_get_updated_procurements_with_raw_data_validation_error(mock_get, repository, caplog):
    """Tests handling of ValidationError in get_updated_procurements_with_raw_data."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = {"invalid": "data"}
    mock_get.return_value = mock_response
    target_date = date(2023, 1, 1)
    result = repository.get_updated_procurements_with_raw_data(target_date)
    assert result == []
    assert "Data validation error on page 1" in caplog.text


def test_publish_procurement_to_pubsub_api_error(repository, mock_procurement, caplog):
    """Tests handling of GoogleAPICallError during pub/sub publish."""
    repository.pubsub_provider.publish.side_effect = exceptions.GoogleAPICallError("Pub/Sub error")
    mock_procurement.model_dump_json.return_value = "{}"

    result = repository.publish_procurement_to_pubsub(mock_procurement)
    assert result is False
    assert "Failed to publish message for 123: None Pub/Sub error" in caplog.text


@patch.object(ProcurementsRepository, "_extract_from_zip", side_effect=Exception("ZIP processing error"))
def test_recursive_file_processing_archive_exception(mock_extract, repository, caplog):
    """Tests that an exception during archive extraction is handled and the file is treated as a single entity."""
    file_collection = []
    repository._recursive_file_processing(
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


def test_get_procurement_by_hash_found(repository):
    """Tests checking a hash that exists."""
    repository.engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = (
        1
    )
    assert repository.get_procurement_by_hash("existing_hash") is True


def test_get_procurement_by_hash_not_found(repository):
    """Tests checking a hash that does not exist."""
    repository.engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = (
        None
    )
    assert repository.get_procurement_by_hash("new_hash") is False


def test_get_procurement_by_id_and_version_not_found(repository):
    """Tests fetching a procurement that does not exist."""
    repository.engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = (
        None
    )
    result = repository.get_procurement_by_id_and_version("123", 1)
    assert result is None


def test_save_procurement_version(repository, mock_procurement):
    """Tests saving a new procurement version."""
    repository.save_procurement_version(mock_procurement, '{"key":"value"}', 1, "hash123")
    assert repository.engine.connect.return_value.__enter__.return_value.execute.call_count == 1
    assert repository.engine.connect.return_value.__enter__.return_value.commit.call_count == 1


@patch("requests.get")
def test_get_updated_procurements_happy_path(mock_get, repository):
    """Tests the happy path for get_updated_procurements."""
    # This response will be returned on the first call
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

    # This response will be returned on all subsequent calls
    mock_response_no_content = MagicMock()
    mock_response_no_content.status_code = HTTPStatus.NO_CONTENT

    # Set the side_effect to return the data response once, then the no_content response forever
    mock_get.side_effect = [mock_response_with_data] + [mock_response_no_content] * 10

    target_date = date(2023, 1, 1)
    result = repository.get_updated_procurements(target_date)
    assert len(result) == 1
    assert result[0].pncp_control_number == "PNCP-123"


@patch("requests.get")
def test_get_updated_procurements_no_content(mock_get, repository):
    """Tests get_updated_procurements with a 204 No Content response."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.NO_CONTENT
    mock_get.return_value = mock_response

    target_date = date(2023, 1, 1)
    result = repository.get_updated_procurements(target_date)
    assert result == []
