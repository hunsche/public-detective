import unittest
from unittest.mock import MagicMock, patch

from source.worker.subscription import Subscription


class TestSubscription(unittest.TestCase):
    @patch("providers.database.DatabaseManager.get_engine")
    @patch("providers.config.ConfigProvider.get_config")
    @patch("services.analysis.AnalysisService")
    @patch("repositories.procurement.ProcurementRepository")
    def test_process_message_validation_error(
        self, _mock_proc_repo, _mock_analysis_service, mock_get_config, mock_get_engine
    ):
        # Arrange
        mock_get_config.return_value = MagicMock()
        mock_get_engine.return_value = MagicMock()
        sub = Subscription()

        mock_message = MagicMock()
        mock_message.data = b"invalid json"
        mock_message.message_id = "123"

        # Act
        sub._process_message(mock_message)

        # Assert
        mock_message.nack.assert_called_once()
        mock_message.ack.assert_not_called()


if __name__ == "__main__":
    unittest.main()
