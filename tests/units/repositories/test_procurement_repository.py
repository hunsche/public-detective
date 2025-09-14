import io
import tarfile
import zipfile
from datetime import date
from unittest.mock import MagicMock, patch

import py7zr
import pytest
import rarfile
import requests
from google.api_core import exceptions
from public_detective.models.procurements import Procurement
from public_detective.repositories.procurements import ProcurementsRepository


def _get_mock_procurement_data(control_number: str) -> dict:
    """Returns a dictionary with minimal valid data for a Procurement model.

    Args:
        control_number: The control number to use for the mock data.

    Returns:
        A dictionary with mock procurement data.
    """
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
    """Fixture for a mocked database engine.

    Returns:
        A MagicMock for the database engine.
    """
    return MagicMock()


@pytest.fixture
def mock_pubsub_provider() -> MagicMock:
    """Fixture for a mocked PubSubProvider.

    Returns:
        A MagicMock for the PubSubProvider.
    """
    return MagicMock()


@pytest.fixture
def repo(mock_engine: MagicMock, mock_pubsub_provider: MagicMock) -> ProcurementsRepository:
    """Provides a ProcurementsRepository instance with mocked dependencies.

    Args:
        mock_engine: The mocked database engine.
        mock_pubsub_provider: The mocked PubSubProvider.

    Returns:
        An instance of ProcurementsRepository.
    """
    with patch("public_detective.providers.config.ConfigProvider.get_config") as mock_get_config:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        return ProcurementsRepository(engine=mock_engine, pubsub_provider=mock_pubsub_provider)


def test_extract_from_zip(repo: ProcurementsRepository) -> None:
    """Tests extracting files from a ZIP archive.

    Args:
        repo: The ProcurementsRepository instance.
    """
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
    """Tests extracting files from a 7z archive.

    Args:
        repo: The ProcurementsRepository instance.
    """
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
    """Tests extracting files from a TAR archive.

    Args:
        repo: The ProcurementsRepository instance.
    """
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
    """Tests successful fetching and filtering of document metadata.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
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
def test_get_all_documents_metadata_request_error(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests handling of request errors when fetching document metadata.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
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
def test_get_all_documents_metadata_empty_list(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests handling of an empty list of documents from the API.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
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
def test_download_file_content_success(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests successful download of file content.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"file content"
    mock_get.return_value = mock_response

    content = repo._download_file_content("http://test.url/file.pdf")

    assert content == b"file content"
    mock_get.assert_called_once_with("http://test.url/file.pdf", timeout=90)


@patch("requests.get")
def test_download_file_content_error(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests handling of request errors during file download.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    mock_get.side_effect = requests.RequestException

    content = repo._download_file_content("http://test.url/file.pdf")

    assert content is None


@patch("requests.get")
def test_get_updated_procurements_with_raw_data_request_error(
    mock_get: MagicMock, repo: ProcurementsRepository
) -> None:
    """Tests that a request exception is handled when fetching raw data.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    mock_get.side_effect = requests.RequestException("API down")
    target_date = date(2025, 1, 1)
    repo.config.TARGET_IBGE_CODES = ["12345"]
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    procurements = repo.get_updated_procurements_with_raw_data(target_date)

    assert procurements == []


@patch("requests.head")
def test_determine_original_filename_success(mock_head: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests successful determination of filename from Content-Disposition header.

    Args:
        mock_head: Mock for requests.head.
        repo: The ProcurementsRepository instance.
    """
    mock_response = MagicMock()
    mock_response.headers = {"Content-Disposition": 'attachment; filename="test_file.pdf"'}
    mock_head.return_value = mock_response

    filename = repo._determine_original_filename("http://test.url/download")

    assert filename == "test_file.pdf"


@patch("requests.head")
def test_determine_original_filename_error(mock_head: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests handling of request errors when determining filename.

    Args:
        mock_head: Mock for requests.head.
        repo: The ProcurementsRepository instance.
    """
    mock_head.side_effect = requests.RequestException
    filename = repo._determine_original_filename("http://test")
    assert filename is None


@patch("requests.head")
def test_determine_original_filename_no_header(mock_head: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests handling of missing Content-Disposition header.

    Args:
        mock_head: Mock for requests.head.
        repo: The ProcurementsRepository instance.
    """
    mock_response = MagicMock()
    mock_response.headers = {}
    mock_head.return_value = mock_response
    filename = repo._determine_original_filename("http://test")
    assert filename is None


def test_create_zip_from_files_success(repo: ProcurementsRepository) -> None:
    """Tests successful creation of a ZIP archive from a list of files.

    Args:
        repo: The ProcurementsRepository instance.
    """
    files = [("file1.txt", b"content1"), ("path/to/file2.txt", b"content2")]

    zip_bytes = repo.create_zip_from_files(files, "control-123")

    assert zip_bytes is not None
    zip_buffer = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        assert "file1.txt" in zf.namelist()
        assert "path_to_file2.txt" in zf.namelist()
        assert zf.read("file1.txt") == b"content1"
        assert zf.read("path_to_file2.txt") == b"content2"


def test_create_zip_from_files_empty_list(repo: ProcurementsRepository) -> None:
    """Tests that no ZIP is created if the file list is empty.

    Args:
        repo: The ProcurementsRepository instance.
    """
    zip_bytes = repo.create_zip_from_files([], "control-123")
    assert zip_bytes is None


def test_publish_procurement_to_pubsub_error(repo: ProcurementsRepository, mock_pubsub_provider: MagicMock) -> None:
    """Tests handling of Google API errors when publishing to Pub/Sub.

    Args:
        repo: The ProcurementsRepository instance.
        mock_pubsub_provider: The mocked PubSubProvider.
    """
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "123"
    procurement.model_dump_json.return_value = '{"key": "value"}'
    mock_pubsub_provider.publish.side_effect = exceptions.GoogleAPICallError("test error")

    result = repo.publish_procurement_to_pubsub(procurement)

    assert result is False


def test_publish_procurement_to_pubsub_success(repo: ProcurementsRepository, mock_pubsub_provider: MagicMock) -> None:
    """Tests successful publishing of a procurement to Pub/Sub.

    Args:
        repo: The ProcurementsRepository instance.
        mock_pubsub_provider: The mocked PubSubProvider.
    """
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "123"
    procurement.model_dump_json.return_value = '{"key": "value"}'
    mock_pubsub_provider.publish.return_value = "message-id-123"

    result = repo.publish_procurement_to_pubsub(procurement)

    assert result is True
    mock_pubsub_provider.publish.assert_called_once()


def test_recursive_file_processing_non_archive(repo: ProcurementsRepository) -> None:
    """Tests that non-archive files are added directly to the collection.

    Args:
        repo: The ProcurementsRepository instance.
    """
    file_collection: list = []
    repo._recursive_file_processing(b"simple content", "file.txt", 0, file_collection)
    assert file_collection == [("file.txt", b"simple content")]


@patch("requests.get")
def test_get_updated_procurements_pagination_and_error_handling(
    mock_get: MagicMock, repo: ProcurementsRepository
) -> None:
    """Tests pagination and error handling in get_updated_procurements.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
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
def test_get_updated_procurements_no_city_codes(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests that a nationwide search is performed if no city codes are configured.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_get.return_value = mock_response

    target_date = date(2025, 1, 1)
    repo.config.TARGET_IBGE_CODES = []
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    repo.get_updated_procurements(target_date)

    # 4 modalities are checked
    assert mock_get.call_count == 4
    for call in mock_get.call_args_list:
        assert "codigoMunicipioIbge" not in call.kwargs["params"]


@patch("requests.get")
def test_get_updated_procurements_request_error(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests that a request exception is handled when fetching procurements.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    mock_get.side_effect = requests.RequestException("API down")
    target_date = date(2025, 1, 1)
    repo.config.TARGET_IBGE_CODES = ["12345"]
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    procurements = repo.get_updated_procurements(target_date)

    assert procurements == []


def test_process_procurement_documents_no_docs(repo: ProcurementsRepository) -> None:
    """Tests that an empty list is returned when no documents are found.

    Args:
        repo: The ProcurementsRepository instance.
    """
    procurement = MagicMock(spec=Procurement)
    with patch.object(repo, "_get_all_documents_metadata", return_value=[]):
        result = repo.process_procurement_documents(procurement)
        assert result == []


def test_process_procurement_documents_download_fails(repo: ProcurementsRepository) -> None:
    """Tests that processing continues even if a document download fails.

    Args:
        repo: The ProcurementsRepository instance.
    """
    procurement = MagicMock(spec=Procurement)
    mock_doc = MagicMock()
    mock_doc.url = "http://fail.com"
    with patch.object(repo, "_get_all_documents_metadata", return_value=[mock_doc]):
        with patch.object(repo, "_download_file_content", return_value=None):
            result = repo.process_procurement_documents(procurement)
            assert result == []


def test_recursive_file_processing_corrupted_archive(repo: ProcurementsRepository) -> None:
    """Tests that a corrupted archive is treated as a single file.

    Args:
        repo: The ProcurementsRepository instance.
    """
    file_collection: list = []
    corrupted_content = b"not a zip"
    with patch.object(repo, "_extract_from_zip", side_effect=zipfile.BadZipFile):
        repo._recursive_file_processing(corrupted_content, "archive.zip", 0, file_collection)
        assert file_collection == [("archive.zip", corrupted_content)]


def test_create_zip_from_files_error(repo: ProcurementsRepository) -> None:
    """Tests that None is returned if zip creation fails.

    Args:
        repo: The ProcurementsRepository instance.
    """
    with patch("zipfile.ZipFile.writestr", side_effect=Exception("zip error")):
        result = repo.create_zip_from_files([("file.txt", b"content")], "control-123")
        assert result is None


@patch("requests.get")
def test_get_all_docs_metadata_no_content(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests handling of 204 No Content status.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    mock_get.return_value.status_code = 204
    procurement = MagicMock(spec=Procurement)
    procurement.government_entity = MagicMock()
    procurement.government_entity.cnpj = "123"
    procurement.procurement_year = "2025"
    procurement.procurement_sequence = "1"
    repo.config.PNCP_INTEGRATION_API_URL = "http://test.api/"
    docs = repo._get_all_documents_metadata(procurement)
    assert docs == []


@patch("requests.head")
def test_determine_original_filename_no_match(mock_head: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests handling of Content-Disposition header with no filename match.

    Args:
        mock_head: Mock for requests.head.
        repo: The ProcurementsRepository instance.
    """
    mock_response = MagicMock()
    mock_response.headers = {"Content-Disposition": "attachment"}
    mock_head.return_value = mock_response
    filename = repo._determine_original_filename("http://test.url/download")
    assert filename is None


def test_get_latest_version(repo: ProcurementsRepository, mock_engine: MagicMock) -> None:
    """Tests retrieving the latest version number for a procurement.

    Args:
        repo: The ProcurementsRepository instance.
        mock_engine: The mocked database engine.
    """
    conn_mock = mock_engine.connect().__enter__()
    conn_mock.execute.return_value.scalar_one_or_none.return_value = 5

    version = repo.get_latest_version("PNCP-123")

    assert version == 5
    conn_mock.execute.assert_called_once()


def test_get_latest_version_none_found(repo: ProcurementsRepository, mock_engine: MagicMock) -> None:
    """Tests retrieving the latest version when none exists.

    Args:
        repo: The ProcurementsRepository instance.
        mock_engine: The mocked database engine.
    """
    conn_mock = mock_engine.connect().__enter__()
    conn_mock.execute.return_value.scalar_one_or_none.return_value = None

    version = repo.get_latest_version("PNCP-123")

    assert version == 0


def test_get_procurement_by_hash(repo: ProcurementsRepository, mock_engine: MagicMock) -> None:
    """Tests checking for a procurement by its content hash.

    Args:
        repo: The ProcurementsRepository instance.
        mock_engine: The mocked database engine.
    """
    conn_mock = mock_engine.connect().__enter__()
    conn_mock.execute.return_value.scalar_one_or_none.return_value = 1

    exists = repo.get_procurement_by_hash("some-hash")

    assert exists is True


def test_get_procurement_by_hash_not_found(repo: ProcurementsRepository, mock_engine: MagicMock) -> None:
    """Tests checking for a procurement by hash when it does not exist.

    Args:
        repo: The ProcurementsRepository instance.
        mock_engine: The mocked database engine.
    """
    conn_mock = mock_engine.connect().__enter__()
    conn_mock.execute.return_value.scalar_one_or_none.return_value = None

    exists = repo.get_procurement_by_hash("some-hash")

    assert exists is False


def test_save_procurement_version(repo: ProcurementsRepository, mock_engine: MagicMock) -> None:
    """Tests saving a new version of a procurement.

    Args:
        repo: The ProcurementsRepository instance.
        mock_engine: The mocked database engine.
    """
    procurement = Procurement.model_validate(_get_mock_procurement_data("PNCP-123"))

    repo.save_procurement_version(procurement, '{"key":"value"}', 2, "some-hash")

    mock_engine.connect.assert_called_once()
    conn_mock = mock_engine.connect().__enter__()
    conn_mock.execute.assert_called_once()
    conn_mock.commit.assert_called_once()


@patch("requests.get")
def test_get_updated_procurements_with_raw_data(mock_get: MagicMock, repo: ProcurementsRepository) -> None:
    """Tests fetching updated procurements with raw data.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    raw_procurement_data = _get_mock_procurement_data("1")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [raw_procurement_data],
        "totalPaginas": 1,
        "numeroPagina": 1,
        "totalRegistros": 1,
    }
    mock_response_empty = MagicMock()
    mock_response_empty.status_code = 204
    mock_get.side_effect = [mock_response, mock_response_empty, mock_response_empty, mock_response_empty]

    target_date = date(2025, 1, 1)
    repo.config.TARGET_IBGE_CODES = ["12345"]
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    procurements = repo.get_updated_procurements_with_raw_data(target_date)

    assert len(procurements) == 1
    assert isinstance(procurements[0][0], Procurement)
    assert isinstance(procurements[0][1], dict)
    assert procurements[0][0].pncp_control_number == "1"
    assert procurements[0][1] == raw_procurement_data


def test_extract_from_rar_error(repo: ProcurementsRepository) -> None:
    """Tests that an empty list is returned if rar extraction fails.

    Args:
        repo: The ProcurementsRepository instance.
    """
    with patch("rarfile.RarFile", side_effect=rarfile.BadRarFile):
        result = repo._extract_from_rar(b"not a rar")
        assert result == []


def test_extract_from_rar_success(repo: ProcurementsRepository) -> None:
    """Tests extracting files from a RAR archive.

    Args:
        repo: The ProcurementsRepository instance.
    """
    mock_rar_info1 = MagicMock()
    mock_rar_info1.filename = "file1.txt"
    mock_rar_info1.isdir.return_value = False

    mock_rar_info2 = MagicMock()
    mock_rar_info2.filename = "file2.txt"
    mock_rar_info2.isdir.return_value = False

    mock_rar_archive = MagicMock()
    mock_rar_archive.infolist.return_value = [mock_rar_info1, mock_rar_info2]
    mock_rar_archive.read.side_effect = [b"content1", b"content2"]

    with patch("rarfile.RarFile") as mock_rar_file_class:
        mock_rar_file_class.return_value.__enter__.return_value = mock_rar_archive
        extracted_files = repo._extract_from_rar(b"dummy rar content")

    assert len(extracted_files) == 2
    assert ("file1.txt", b"content1") in extracted_files
    assert ("file2.txt", b"content2") in extracted_files


@patch("requests.get")
def test_get_updated_procurements_with_raw_data_no_city_codes(
    mock_get: MagicMock, repo: ProcurementsRepository
) -> None:
    """
    Tests that a nationwide search is performed for raw data if no city codes are configured.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_get.return_value = mock_response

    target_date = date(2025, 1, 1)
    repo.config.TARGET_IBGE_CODES = []
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    repo.get_updated_procurements_with_raw_data(target_date)

    assert mock_get.call_count == 4
    for call in mock_get.call_args_list:
        assert "codigoMunicipioIbge" not in call.kwargs["params"]


def test_get_procurement_by_id_and_version_not_found(repo: ProcurementsRepository, mock_engine: MagicMock) -> None:
    """
    Tests that None is returned when a procurement is not found by ID and version.

    Args:
        repo: The ProcurementsRepository instance.
        mock_engine: The mocked database engine.
    """
    conn_mock = mock_engine.connect().__enter__()
    conn_mock.execute.return_value.scalar_one_or_none.return_value = None

    result = repo.get_procurement_by_id_and_version("PNCP-999", 1)

    assert result is None


def test_recursive_file_processing_7z(repo: ProcurementsRepository) -> None:
    """Tests that .7z files are dispatched to the correct handler.

    Args:
        repo: The ProcurementsRepository instance.
    """
    with patch.object(repo, "_extract_from_7z") as mock_extract:
        repo._recursive_file_processing(b"dummy", "test.7z", 0, [])
        mock_extract.assert_called_once()


def test_recursive_file_processing_tar(repo: ProcurementsRepository) -> None:
    """Tests that .tar files are dispatched to the correct handler.

    Args:
        repo: The ProcurementsRepository instance.
    """
    with patch("tarfile.is_tarfile", return_value=True):
        with patch.object(repo, "_extract_from_tar") as mock_extract:
            repo._recursive_file_processing(b"dummy", "test.tar", 0, [])
            mock_extract.assert_called_once()


def test_extract_from_zip_with_dir(repo: ProcurementsRepository) -> None:
    """Tests that directories in ZIP archives are ignored.

    Args:
        repo: The ProcurementsRepository instance.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("dir/", "")
        zf.writestr("file1.txt", "content1")
    zip_content = zip_buffer.getvalue()

    extracted_files = repo._extract_from_zip(zip_content)
    assert len(extracted_files) == 1
    assert extracted_files[0][0] == "file1.txt"


def test_extract_from_rar_with_dir(repo: ProcurementsRepository) -> None:
    """Tests that directories in RAR archives are ignored.

    Args:
        repo: The ProcurementsRepository instance.
    """
    mock_rar_info_dir = MagicMock()
    mock_rar_info_dir.filename = "dir/"
    mock_rar_info_dir.isdir.return_value = True

    mock_rar_info_file = MagicMock()
    mock_rar_info_file.filename = "file1.txt"
    mock_rar_info_file.isdir.return_value = False

    mock_rar_archive = MagicMock()
    mock_rar_archive.infolist.return_value = [mock_rar_info_dir, mock_rar_info_file]
    mock_rar_archive.read.return_value = b"content1"

    with patch("rarfile.RarFile") as mock_rar_file_class:
        mock_rar_file_class.return_value.__enter__.return_value = mock_rar_archive
        extracted_files = repo._extract_from_rar(b"dummy rar content")

    assert len(extracted_files) == 1
    assert extracted_files[0][0] == "file1.txt"


def test_extract_from_tar_with_dir_and_none_file(repo: ProcurementsRepository) -> None:
    """Tests that directories and None file objects in TAR archives are handled.

    Args:
        repo: The ProcurementsRepository instance.
    """
    mock_tar_info_dir = MagicMock()
    mock_tar_info_dir.name = "dir/"
    mock_tar_info_dir.isfile.return_value = False

    mock_tar_info_file = MagicMock()
    mock_tar_info_file.name = "file1.txt"
    mock_tar_info_file.isfile.return_value = True

    mock_tar_archive = MagicMock()
    mock_tar_archive.getmembers.return_value = [mock_tar_info_dir, mock_tar_info_file]
    mock_tar_archive.extractfile.return_value = None  # Simulate case where file cannot be extracted

    with patch("tarfile.open") as mock_tar_open:
        mock_tar_open.return_value.__enter__.return_value = mock_tar_archive
        extracted_files = repo._extract_from_tar(b"dummy tar content")

    assert len(extracted_files) == 0
    mock_tar_archive.extractfile.assert_called_once_with(mock_tar_info_file)


@patch("requests.get")
def test_get_updated_procurements_with_raw_data_validation_error(
    mock_get: MagicMock, repo: ProcurementsRepository
) -> None:
    """Tests that a validation error is handled when fetching raw data.

    Args:
        mock_get: Mock for requests.get.
        repo: The ProcurementsRepository instance.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"invalid": "data"}]}
    mock_get.return_value = mock_response

    target_date = date(2025, 1, 1)
    repo.config.TARGET_IBGE_CODES = ["12345"]
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    procurements = repo.get_updated_procurements_with_raw_data(target_date)

    assert procurements == []
