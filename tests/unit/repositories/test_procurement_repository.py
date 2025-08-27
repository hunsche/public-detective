import io
import zipfile
from unittest.mock import patch, MagicMock

import pytest
from repositories.procurement import ProcurementRepository


@pytest.fixture
def repo() -> ProcurementRepository:
    """Fixture to create a ProcurementRepository with mocked dependencies."""
    with (
        patch("providers.database.DatabaseManager.get_engine"),
        patch("providers.config.ConfigProvider.get_config"),
        patch("providers.pubsub.PubSubProvider"),
    ):
        repository = ProcurementRepository()
        repository.logger = MagicMock()
        return repository


def test_extract_from_zip(repo: ProcurementRepository):
    """Tests that ZIP file contents are extracted correctly."""
    # Arrange
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("file1.txt", b"content1")
        zf.writestr("file2.txt", b"content2")
    zip_content = zip_buffer.getvalue()

    # Act
    extracted_files = repo._extract_from_zip(zip_content)

    # Assert
    assert len(extracted_files) == 2
    assert ("file1.txt", b"content1") in extracted_files
    assert ("file2.txt", b"content2") in extracted_files


def test_create_zip_from_files_success(repo: ProcurementRepository):
    """Tests successful creation of a ZIP file from a list of files."""
    # Arrange
    files = [("file1.txt", b"content1"), ("path/to/file2.txt", b"content2")]
    control_number = "12345"

    # Act
    zip_bytes = repo.create_zip_from_files(files, control_number)

    # Assert
    assert zip_bytes is not None
    repo.logger.info.assert_called()

    # Verify zip contents
    zip_buffer = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_buffer, "r") as zf:
        # Check that invalid characters are replaced
        assert set(zf.namelist()) == {"file1.txt", "path/to/file2.txt"}
        assert zf.read("file1.txt") == b"content1"
        assert zf.read("path/to/file2.txt") == b"content2"


def test_create_zip_from_files_empty(repo: ProcurementRepository):
    """Tests that no ZIP file is created when the file list is empty."""
    # Arrange
    files: list[tuple[str, bytes]] = []
    control_number = "12345"

    # Act
    zip_bytes = repo.create_zip_from_files(files, control_number)

    # Assert
    assert zip_bytes is None
    repo.logger.info.assert_not_called()


def test_create_zip_from_files_exception(repo: ProcurementRepository):
    """Tests that an error is logged if ZIP creation fails."""
    # Arrange
    files: list[tuple[str, bytes]] = [("file1.txt", b"content1")]
    control_number = "12345"
    error_message = "zip error"

    # Act
    with patch("zipfile.ZipFile", side_effect=Exception(error_message)):
        zip_bytes = repo.create_zip_from_files(files, control_number)

    # Assert
    assert zip_bytes is None
    repo.logger.error.assert_called_with(f"Failed to create final ZIP archive for {control_number}: {error_message}")
