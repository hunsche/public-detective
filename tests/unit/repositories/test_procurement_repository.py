import io
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from repositories.procurement import ProcurementRepository


class TestProcurementRepository(unittest.TestCase):
    @patch("providers.database.DatabaseManager.get_engine")
    @patch("providers.config.ConfigProvider.get_config")
    def test_extract_from_zip(self, mock_get_config, mock_get_engine):
        # Arrange
        mock_get_config.return_value = MagicMock()
        mock_get_engine.return_value = MagicMock()
        repo = ProcurementRepository()

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("file1.txt", b"content1")
            zf.writestr("file2.txt", b"content2")
        zip_content = zip_buffer.getvalue()

        # Act
        extracted_files = repo._extract_from_zip(zip_content)

        # Assert
        self.assertEqual(len(extracted_files), 2)
        self.assertIn(("file1.txt", b"content1"), extracted_files)
        self.assertIn(("file2.txt", b"content2"), extracted_files)


if __name__ == "__main__":
    unittest.main()
