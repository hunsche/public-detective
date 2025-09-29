"""
Unit tests for the ProcurementsRepository to increase test coverage.
"""
from unittest.mock import MagicMock, patch
from datetime import date

import pytest
import requests
import rarfile
from pydantic import ValidationError
from google.api_core import exceptions
from public_detective.models.procurements import Procurement
from public_detective.repositories.procurements import ProcurementsRepository


def test_extract_from_rar_bad_file(repo: ProcurementsRepository):
    """Tests that a BadRarFile exception is handled correctly."""
    with patch("rarfile.RarFile", side_effect=rarfile.BadRarFile):
        result = repo._extract_from_rar(b"corrupted content")
        assert result == []
    repo.logger.warning.assert_called_once_with("Failed to extract from a corrupted or invalid RAR file.")


def test_create_zip_from_files_empty(repo: ProcurementsRepository):
    """Tests that create_zip_from_files returns None for an empty file list."""
    result = repo.create_zip_from_files([], "test_control")
    assert result is None


def test_create_zip_from_files_exception(repo: ProcurementsRepository):
    """Tests that create_zip_from_files handles exceptions during zip creation."""
    with patch("zipfile.ZipFile", side_effect=Exception("zip error")):
        result = repo.create_zip_from_files([("file.txt", b"content")], "test_control")
        assert result is None
    repo.logger.error.assert_called_once()


@patch("requests.get")
def test_download_file_content_fails(mock_get: MagicMock, repo: ProcurementsRepository):
    """Tests that download_file_content returns None when the request fails."""
    mock_get.side_effect = requests.RequestException("Request failed")
    result = repo._download_file_content("http://test.url")
    assert result is None
    repo.logger.error.assert_called_once()


@patch("requests.head")
def test_determine_original_filename_fails(mock_head: MagicMock, repo: ProcurementsRepository):
    """Tests that determine_original_filename returns None when the request fails."""
    mock_head.side_effect = requests.RequestException("Request failed")
    result = repo._determine_original_filename("http://test.url")
    assert result is None
    repo.logger.warning.assert_called_once()

@patch("requests.head")
def test_determine_original_filename_success(mock_head: MagicMock, repo: ProcurementsRepository):
    """Tests that determine_original_filename extracts the filename correctly."""
    mock_response = MagicMock()
    mock_response.headers = {"Content-Disposition": 'attachment; filename="test_file.pdf"'}
    mock_head.return_value = mock_response

    result = repo._determine_original_filename("http://test.url")
    assert result == "test_file.pdf"


@patch("requests.get")
def test_get_updated_procurements_request_exception(mock_get: MagicMock, repo: ProcurementsRepository):
    """Tests get_updated_procurements handles request exceptions."""
    mock_get.side_effect = requests.RequestException("API Error")
    repo.config.TARGET_IBGE_CODES = ["12345"]
    result = repo.get_updated_procurements(target_date=date(2025,1,1))
    assert result == []
    repo.logger.error.assert_called()


@patch("requests.get")
def test_get_updated_procurements_with_raw_data_validation_error(mock_get: MagicMock, repo: ProcurementsRepository):
    """Tests get_updated_procurements_with_raw_data handles validation errors."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"invalid_field": "value"}]}
    mock_get.return_value = mock_response
    repo.config.TARGET_IBGE_CODES = ["12345"]

    result = repo.get_updated_procurements_with_raw_data(target_date=date(2025,1,1))

    assert result == []
    repo.logger.error.assert_called()

@patch("requests.get")
def test_get_updated_procurements_no_ibge_codes(mock_get: MagicMock, repo: ProcurementsRepository):
    """Tests get_updated_procurements when no IBGE codes are configured."""
    mock_response = MagicMock()
    mock_response.status_code = 204 # No content
    mock_get.return_value = mock_response
    repo.config.TARGET_IBGE_CODES = []

    repo.get_updated_procurements(target_date=date(2025,1,1))

    repo.logger.warning.assert_called_with("No TARGET_IBGE_CODES configured. The search will be nationwide.")
    assert "codigoMunicipioIbge" not in mock_get.call_args.kwargs["params"]

def test_publish_procurement_to_pubsub_fails(repo: ProcurementsRepository, mock_procurement: Procurement):
    """Tests that publish_procurement_to_pubsub handles API errors."""
    repo.pubsub_provider.publish.side_effect = exceptions.GoogleAPICallError("API Error")

    result = repo.publish_procurement_to_pubsub(mock_procurement)

    assert result is False
    repo.logger.error.assert_called_once()

def test_get_latest_version_none_found(repo: ProcurementsRepository):
    """Tests get_latest_version when no versions are found for the control number."""
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = None
    result = repo.get_latest_version("PNCP123")
    assert result == 0

@patch("requests.get")
def test_get_all_documents_metadata_no_content(mock_get: MagicMock, repo: ProcurementsRepository, mock_procurement: Procurement):
    """Tests _get_all_documents_metadata when the API returns a 204 No Content."""
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_get.return_value = mock_response

    result = repo._get_all_documents_metadata(mock_procurement)
    assert result == []

def test_get_procurement_by_id_and_version_not_found(repo: ProcurementsRepository):
    """Tests get_procurement_by_id_and_version when no record is found."""
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = None
    result = repo.get_procurement_by_id_and_version("PNCP123", 1)
    assert result is None

def test_get_procurement_by_hash_not_found(repo: ProcurementsRepository):
    """Tests get_procurement_by_hash when no record is found."""
    repo.engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = None
    result = repo.get_procurement_by_hash("some_hash")
    assert result is False

def test_publish_procurement_to_pubsub_success(repo: ProcurementsRepository, mock_procurement: Procurement):
    """Tests successful publishing to Pub/Sub."""
    repo.pubsub_provider.publish.return_value = "message_id"
    result = repo.publish_procurement_to_pubsub(mock_procurement)
    assert result is True
    repo.logger.debug.assert_called_once()