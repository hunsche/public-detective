import unittest
from unittest.mock import MagicMock, patch

from models.file_record import NewFileRecord
from repositories.file_record import FileRecordRepository


class TestFileRecordRepository(unittest.TestCase):
    @patch("providers.database.DatabaseManager.get_engine")
    def test_save_file_record(self, mock_get_engine):
        # Arrange
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        repo = FileRecordRepository()
        record = NewFileRecord(
            analysis_id=1,
            file_name="test.pdf",
            gcs_path="test/gcs/path",
            extension=".pdf",
            size_bytes=1234,
            nesting_level=0,
            included_in_analysis=True,
            exclusion_reason=None,
            prioritization_logic="high",
        )

        # Act
        repo.save_file_record(record)

        # Assert
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
