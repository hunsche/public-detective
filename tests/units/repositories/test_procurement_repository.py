import bz2
import gzip
import io
import logging
import lzma
import tarfile
import zipfile
from collections.abc import Callable, Iterable
from datetime import date
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import MagicMock, patch

import py7zr
import pytest
import rarfile
import requests
from google.api_core import exceptions
from public_detective.models.procurements import Procurement, ProcurementDocument, ProcurementListResponse
from public_detective.repositories.procurements import ProcessedFile, ProcurementsRepository
from pydantic import ValidationError

SAMPLE_CONTENT = b"sample-content"


if not hasattr(rarfile, "NeedPassword"):

    class NeedPasswordFallback(rarfile.Error):
        """Compatibility shim for rarfile versions without NeedPassword."""

    rarfile.NeedPassword = NeedPasswordFallback


def create_zip_payload(files: list[tuple[str, bytes]]) -> bytes:
    """Creates a ZIP payload from a list of files."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        for filename, content in files:
            zf.writestr(filename, content)
    return zip_buffer.getvalue()


def create_tar_payload(
    files: list[tuple[str, bytes]],
    mode: Literal["w", "w:gz", "w:bz2", "w:xz"] = "w",
) -> bytes:
    """Creates a TAR payload from a list of files."""
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode=mode) as tar:
        for filename, content in files:
            info = tarfile.TarInfo(name=filename)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return tar_buffer.getvalue()


def create_7z_payload(files: list[tuple[str, bytes]]) -> bytes:
    """Creates a 7z payload from a list of files."""
    s_buffer = io.BytesIO()
    with py7zr.SevenZipFile(s_buffer, "w") as archive:
        for filename, content in files:
            archive.writestr(content, filename)
    return s_buffer.getvalue()


def create_gzip_payload(content: bytes) -> bytes:
    """Compresses content using gzip."""
    return gzip.compress(content)


def create_bzip2_payload(content: bytes) -> bytes:
    """Compresses content using bzip2."""
    return bz2.compress(content)


def create_xz_payload(content: bytes) -> bytes:
    """Compresses content using lzma/xz."""
    return lzma.compress(content)


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


def test_extract_from_zip_member_read_error(repo: ProcurementsRepository) -> None:
    """Propagates ValueError when a ZIP member cannot be read."""
    mock_member = MagicMock()
    mock_member.is_dir.return_value = False
    mock_member.filename = "broken.txt"

    mock_archive = MagicMock()
    mock_archive.infolist.return_value = [mock_member]
    mock_archive.read.side_effect = ValueError("broken member")

    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_archive
    with patch("zipfile.ZipFile", return_value=mock_context):
        with pytest.raises(ValueError, match="broken member"):
            repo._extract_from_zip(b"dummy content")


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


@patch("os.chmod")
@patch("os.walk")
@patch("py7zr.SevenZipFile")
def test_extract_from_7z_permission_error(
    mock_seven_zip: MagicMock,
    mock_os_walk: MagicMock,
    mock_chmod: MagicMock,
    repo: ProcurementsRepository,
    caplog: Any,
) -> None:
    """Retries reading files when a PermissionError occurs."""
    caplog.set_level(logging.WARNING)

    mock_archive = MagicMock()
    mock_seven_zip.return_value.__enter__.return_value = mock_archive

    def fake_walk(tmpdir: str) -> Iterable[tuple[str, list[str], list[str]]]:
        yield tmpdir, [], ["restricted.txt"]

    mock_os_walk.side_effect = fake_walk

    file_handle = MagicMock()
    file_handle.__enter__.return_value.read.return_value = b"permitted"
    file_handle.__exit__.return_value = None

    with patch("builtins.open", side_effect=[PermissionError("denied"), file_handle]):
        extracted = repo._extract_from_7z(b"content")

    assert extracted == [("restricted.txt", b"permitted")]
    assert mock_chmod.called


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


def test_download_file_content_empty_body(repo: ProcurementsRepository) -> None:
    """Returns None when the response body is empty."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b""
    repo.http_provider.get.return_value = mock_response
    assert repo._download_file_content("http://test.url/file.pdf") is None


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


def test_process_procurement_documents_no_metadata(repo: ProcurementsRepository) -> None:
    """Returns an empty list when there are no documents to process."""
    procurement = MagicMock(spec=Procurement)
    with patch.object(repo, "_get_all_documents_metadata", return_value=[]):
        assert repo.process_procurement_documents(procurement) == []


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
        assert file_collection[0].extraction_failed is True


def test_recursive_file_processing_single_file_decompress_error(repo: ProcurementsRepository) -> None:
    """Marks single-file archives as failed when decompression raises errors."""
    file_collection: list[ProcessedFile] = []
    failing_decompressor = MagicMock(side_effect=ValueError("boom"))
    with patch.dict(
        ProcurementsRepository._SINGLE_FILE_COMPRESSION_HANDLERS,
        {".gz": failing_decompressor},
        clear=False,
    ):
        repo._recursive_file_processing(
            source_document_id="src-doc-2",
            content=b"compressed",
            current_path="document.txt.gz",
            nesting_level=0,
            file_collection=file_collection,
            raw_document_metadata={"origin": "test"},
        )

    assert len(file_collection) == 1
    processed = file_collection[0]
    assert processed.relative_path == "document.txt.gz"
    assert processed.extraction_failed is True


@pytest.mark.parametrize(
    ("current_path", "payload_factory", "expected_paths"),
    [
        ("archive.zip", lambda: create_zip_payload([("inner.txt", SAMPLE_CONTENT)]), ["archive.zip/inner.txt"]),
        ("archive.tar", lambda: create_tar_payload([("inner.txt", SAMPLE_CONTENT)]), ["archive.tar/inner.txt"]),
        (
            "archive.tgz",
            lambda: create_tar_payload([("inner.txt", SAMPLE_CONTENT)], mode="w:gz"),
            ["archive.tgz/inner.txt"],
        ),
        (
            "archive.tar.gz",
            lambda: create_tar_payload([("inner.txt", SAMPLE_CONTENT)], mode="w:gz"),
            ["archive.tar.gz/inner.txt"],
        ),
        (
            "archive.tbz",
            lambda: create_tar_payload([("inner.txt", SAMPLE_CONTENT)], mode="w:bz2"),
            ["archive.tbz/inner.txt"],
        ),
        (
            "archive.tbz2",
            lambda: create_tar_payload([("inner.txt", SAMPLE_CONTENT)], mode="w:bz2"),
            ["archive.tbz2/inner.txt"],
        ),
        (
            "archive.tar.bz2",
            lambda: create_tar_payload([("inner.txt", SAMPLE_CONTENT)], mode="w:bz2"),
            ["archive.tar.bz2/inner.txt"],
        ),
        (
            "archive.tar.xz",
            lambda: create_tar_payload([("inner.txt", SAMPLE_CONTENT)], mode="w:xz"),
            ["archive.tar.xz/inner.txt"],
        ),
        (
            "document.txt.gz",
            lambda: create_gzip_payload(SAMPLE_CONTENT),
            ["document.txt"],
        ),
        (
            "document.txt.bz",
            lambda: create_bzip2_payload(SAMPLE_CONTENT),
            ["document.txt"],
        ),
        (
            "document.txt.bz2",
            lambda: create_bzip2_payload(SAMPLE_CONTENT),
            ["document.txt"],
        ),
        (
            "document.txt.xz",
            lambda: create_xz_payload(SAMPLE_CONTENT),
            ["document.txt"],
        ),
        (
            "archive.7z",
            lambda: create_7z_payload([("inner.txt", SAMPLE_CONTENT)]),
            ["archive.7z/inner.txt"],
        ),
    ],
)
def test_recursive_file_processing_supported_archives(
    repo: ProcurementsRepository,
    current_path: str,
    payload_factory: Callable[[], bytes],
    expected_paths: list[str],
) -> None:
    """Ensures that all supported archive formats are processed correctly."""
    file_collection: list[ProcessedFile] = []
    repo._recursive_file_processing(
        source_document_id="src-doc-1",
        content=payload_factory(),
        current_path=current_path,
        nesting_level=0,
        file_collection=file_collection,
        raw_document_metadata={"meta": True},
    )

    assert [record.relative_path for record in file_collection] == expected_paths
    for record in file_collection:
        assert record.content == SAMPLE_CONTENT
        assert record.extraction_failed is False


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

    def test_recursive_file_processing_rar_success(repo: ProcurementsRepository) -> None:
        """Tests that RAR archives are expanded into individual files."""
        file_collection: list[ProcessedFile] = []
        with patch.object(repo, "_extract_from_rar", return_value=[("inner.txt", SAMPLE_CONTENT)]):
            repo._recursive_file_processing(
                source_document_id="src-doc-1",
                content=b"rar-bytes",
                current_path="archive.rar",
                nesting_level=0,
                file_collection=file_collection,
                raw_document_metadata={"rar": True},
            )

        assert len(file_collection) == 1
        record = file_collection[0]
        assert record.relative_path == "archive.rar/inner.txt"
        assert record.content == SAMPLE_CONTENT
        assert record.extraction_failed is False


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
    """Tests that a BadRarFile error triggers a runtime error with logging."""
    with patch("rarfile.RarFile", side_effect=rarfile.BadRarFile("bad")):
        with pytest.raises(RuntimeError, match="Failed to extract from RAR archive"):
            repo._extract_from_rar(b"bad content")
    assert "Failed to extract from a corrupted or invalid RAR file" in caplog.text


def test_extract_from_rar_member_read_error(repo: ProcurementsRepository) -> None:
    """Raises a runtime error when a RAR member cannot be read."""
    mock_member = MagicMock()
    mock_member.isdir.return_value = False
    mock_member.filename = "doc.txt"
    mock_archive = MagicMock()
    mock_archive.infolist.return_value = [mock_member]
    mock_archive.read.side_effect = rarfile.Error("read error")

    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_archive

    with patch("rarfile.RarFile", return_value=mock_context):
        with pytest.raises(RuntimeError, match="Failed to read member 'doc.txt'"):
            repo._extract_from_rar(b"content")


def test_extract_from_rar_need_password(repo: ProcurementsRepository) -> None:
    """Transforms NeedPassword into a runtime error."""
    with patch("rarfile.RarFile", side_effect=rarfile.NeedPassword("pw")):
        with pytest.raises(RuntimeError, match="Password-protected RAR archives are not supported"):
            repo._extract_from_rar(b"content")


def test_extract_from_rar_unexpected_error(repo: ProcurementsRepository) -> None:
    """Transforms other rarfile errors into runtime exceptions."""
    with patch("rarfile.RarFile", side_effect=rarfile.Error("unexpected")):
        with pytest.raises(RuntimeError, match="Unexpected RAR extraction error"):
            repo._extract_from_rar(b"content")


def test_recursive_file_processing_rar_extraction_failure(repo: ProcurementsRepository) -> None:
    """Tests that RAR extraction failures mark the archive as extraction_failed."""
    file_collection: list[ProcessedFile] = []
    with patch.object(repo, "_extract_from_rar", side_effect=RuntimeError("boom")):
        repo._recursive_file_processing(
            source_document_id="src-doc-1",
            content=b"content",
            current_path="archive.rar",
            nesting_level=0,
            file_collection=file_collection,
            raw_document_metadata={"meta": True},
        )
    assert len(file_collection) == 1
    assert file_collection[0].relative_path == "archive.rar"
    assert file_collection[0].extraction_failed is True


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


def test_process_procurement_documents_happy_path(repo: ProcurementsRepository) -> None:
    """Ensure a non-archive document is processed and returned as a ProcessedFile."""
    # Create a mock ProcurementDocument-like object
    mock_doc = MagicMock()
    mock_doc.url = "http://example.com/file.pdf"
    mock_doc.title = "file.pdf"
    mock_doc.cnpj = "12345678000199"
    mock_doc.procurement_year = 2025
    mock_doc.procurement_sequence = 1
    mock_doc.document_sequence = 1

    raw_meta = {"some": "meta"}

    with (
        patch.object(repo, "_get_all_documents_metadata", return_value=[(mock_doc, raw_meta)]),
        patch.object(repo, "_download_file_content", return_value=b"hello"),
        patch.object(repo, "_determine_original_filename", return_value=None),
    ):
        result = repo.process_procurement_documents(MagicMock(spec=Procurement))
        assert isinstance(result, list)
        assert len(result) == 1
        pf = result[0]
        assert isinstance(pf, ProcessedFile)
        assert pf.content == b"hello"
        assert pf.raw_document_metadata == raw_meta


def test_create_zip_from_files_success(repo: ProcurementsRepository) -> None:
    """Ensure zip is created successfully and contains expected files."""
    files = [("a/b.txt", b"one"), ("c:d.txt", b"two")]
    result = repo.create_zip_from_files(files, "CTRL-1")
    assert result is not None
    # Verify zip contents
    with io.BytesIO(result) as stream:
        with zipfile.ZipFile(stream) as zf:
            names = zf.namelist()
            # paths should be sanitized (':' replaced)
            assert any("b.txt" in n for n in names)
            assert any("c_d.txt" in n or "c:d.txt" not in n for n in names)


def test_publish_procurement_to_pubsub_success(repo: ProcurementsRepository) -> None:
    """Publish returns True on successful publish."""
    mock_proc = MagicMock(spec=Procurement)
    mock_proc.model_dump_json.return_value = '{"ok": true}'
    mock_proc.pncp_control_number = "PNCP-1"
    repo.pubsub_provider.publish.return_value = "message-id"
    assert repo.publish_procurement_to_pubsub(mock_proc) is True


def test_get_updated_procurements_no_target_codes(
    repo: ProcurementsRepository, caplog: pytest.LogCaptureFixture
) -> None:
    """When TARGET_IBGE_CODES is empty, the method should warn and proceed nationwide."""
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy"
    repo.config.TARGET_IBGE_CODES = []
    # Ensure the HTTP call returns NO_CONTENT immediately
    mock_response = MagicMock()
    mock_response.status_code = 204
    repo.http_provider.get.return_value = mock_response
    result = repo.get_updated_procurements(date(2023, 1, 1))
    assert result == []
    assert "No TARGET_IBGE_CODES configured" in caplog.text


def test_recursive_processing_nested_handler(repo: ProcurementsRepository) -> None:
    """When handler returns nested files, recursion should produce correctly nested paths."""
    file_collection: list[ProcessedFile] = []

    # Make the zip handler return a single inner file
    with patch.object(repo, "_extract_from_zip", return_value=[("inner.txt", b"data")]):
        repo._recursive_file_processing(
            source_document_id="s1",
            content=b"dummy",
            current_path="outer.zip",
            nesting_level=0,
            file_collection=file_collection,
            raw_document_metadata={},
        )

    assert len(file_collection) == 1
    assert file_collection[0].relative_path.endswith("outer.zip/inner.txt")


def test_recursive_processing_tar_handler_branch(repo: ProcurementsRepository) -> None:
    """Force tarfile.is_tarfile to True and ensure tar handler is invoked and results collected."""
    file_collection: list[ProcessedFile] = []
    with patch("tarfile.is_tarfile", return_value=True):
        with patch.object(repo, "_extract_from_tar", return_value=[("a.txt", b"x")]):
            repo._recursive_file_processing(
                source_document_id="s2",
                content=b"dummy tar",
                current_path="somefile",
                nesting_level=0,
                file_collection=file_collection,
                raw_document_metadata={},
            )

    # The handler returns a member that should be processed and added
    assert any("a.txt" in f.relative_path for f in file_collection)


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
    result = list(repo.get_updated_procurements_with_raw_data(target_date))
    procurements = [item for event, item in result if event == "procurements_page"]
    assert procurements == []
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
    result = list(repo.get_updated_procurements_with_raw_data(target_date))
    procurements = [item for event, item in result if event == "procurements_page"]
    assert procurements == []
    assert "Data validation error on page 1" in caplog.text


def test_get_updated_procurements_with_raw_data_no_content(repo: ProcurementsRepository) -> None:
    """Tests get_updated_procurements_with_raw_data with a 204 No Content response."""
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.NO_CONTENT
    repo.http_provider.get.return_value = mock_response
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    target_date = date(2023, 1, 1)
    result = list(repo.get_updated_procurements_with_raw_data(target_date))
    procurements = [item for event, item in result if event == "procurements_page"]
    assert procurements == []


def test_get_updated_procurements_with_raw_data_empty_page(repo: ProcurementsRepository, caplog: Any) -> None:
    """Logs a warning and yields no procurements when pages are empty."""
    caplog.set_level(logging.INFO)
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = []

    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = {"data": []}
    repo.http_provider.get.return_value = mock_response

    with patch.object(
        ProcurementListResponse,
        "model_validate",
        side_effect=lambda _raw: SimpleNamespace(data=[], total_pages=1),
    ):
        events = list(repo.get_updated_procurements_with_raw_data(date(2023, 1, 1)))

    assert any(event == "modality_started" for event, _ in events)
    assert any(event == "pages_total" for event, _ in events)
    assert all(event != "procurements_page" for event, _ in events)
    assert "The search will be nationwide" in caplog.text


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

    result = list(repo.get_updated_procurements_with_raw_data(target_date))
    procurements = [item for event, item in result if event == "procurements_page"]

    assert len(procurements) == 1
    procurement_model, raw_data = procurements[0]
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

    result = list(repo.get_updated_procurements_with_raw_data(target_date))
    procurements = [item for event, item in result if event == "procurements_page"]

    assert len(procurements) == 2
    assert procurements[0][0].pncp_control_number == "PNCP-RAW-PAGE-1"
    assert procurements[1][0].pncp_control_number == "PNCP-RAW-PAGE-2"
    assert procurements[0][1] == raw_proc_page1
    assert procurements[1][1] == raw_proc_page2


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


def test_get_updated_procurements_empty_page(repo: ProcurementsRepository) -> None:
    """Stops pagination when a page contains no procurements."""
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://dummy.url"
    repo.config.TARGET_IBGE_CODES = [None]
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = {"data": []}
    repo.http_provider.get.return_value = mock_response

    with patch.object(
        ProcurementListResponse,
        "model_validate",
        side_effect=lambda _raw: SimpleNamespace(data=[], total_pages=1),
    ):
        result = repo.get_updated_procurements(date(2023, 1, 1))

    assert result == []


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


def test_get_procurement_by_control_number_success(repo: ProcurementsRepository) -> None:
    """Tests fetching a single procurement by control number successfully."""
    control_number = "12345678000199-1-123456/2024"
    raw_data = _get_mock_procurement_data(control_number)
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = raw_data
    repo.http_provider.get.return_value = mock_response
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    procurement, result_raw_data = repo.get_procurement_by_control_number(control_number)

    assert procurement is not None
    assert isinstance(procurement, Procurement)
    assert procurement.pncp_control_number == control_number
    assert result_raw_data == raw_data
    repo.http_provider.get.assert_called_once_with("http://test.api/orgaos/12345678000199/compras/2024/123456")


def test_get_procurement_by_control_number_not_found(repo: ProcurementsRepository, caplog: Any) -> None:
    """Tests fetching a single procurement that is not found (404)."""
    control_number = "12345678000199-1-123456/2024"
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.NOT_FOUND
    mock_response.raise_for_status.side_effect = requests.HTTPError
    repo.http_provider.get.return_value = mock_response
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    procurement, raw_data = repo.get_procurement_by_control_number(control_number)

    assert procurement is None
    assert raw_data is None
    assert f"Failed to get/validate procurement for {control_number}" in caplog.text


def test_get_procurement_by_control_number_invalid_format(repo: ProcurementsRepository) -> None:
    """Returns None for control numbers that do not match the expected pattern."""
    result = repo.get_procurement_by_control_number("invalid-control")

    assert result == (None, None)
    repo.http_provider.get.assert_not_called()


def test_get_procurement_by_control_number_validation_error(repo: ProcurementsRepository) -> None:
    """Handles validation errors when parsing the procurement payload."""
    control_number = "12345678000199-1-123456/2024"
    raw_data = _get_mock_procurement_data(control_number)
    mock_response = MagicMock()
    mock_response.status_code = HTTPStatus.OK
    mock_response.json.return_value = raw_data
    repo.http_provider.get.return_value = mock_response
    repo.config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"

    validation_error = ValidationError.from_exception_data("Procurement", [])
    with patch.object(Procurement, "model_validate", side_effect=validation_error):
        procurement, returned_raw = repo.get_procurement_by_control_number(control_number)

    assert procurement is None
    assert returned_raw is None
