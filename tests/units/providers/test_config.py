"""
Unit tests for the ConfigProvider.
"""

from unittest.mock import patch

from providers.config import ConfigProvider


def test_get_config_returns_config_instance() -> None:
    """
    Tests that get_config returns an instance of Config.
    """
    with patch("providers.config.Config") as mock_config_constructor:
        config = ConfigProvider.get_config()
        mock_config_constructor.assert_called_once()
        assert config is not None
