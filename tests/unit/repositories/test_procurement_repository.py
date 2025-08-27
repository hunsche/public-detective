import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest
import requests
from models.procurement import Procurement
from repositories.procurement import ProcurementRepository


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
    # We still need to patch ConfigProvider as it's a direct dependency
    with patch("providers.config.ConfigProvider.get_config"):
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
