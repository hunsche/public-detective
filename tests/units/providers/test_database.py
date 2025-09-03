from unittest.mock import MagicMock, patch

import pytest
from providers.config import Config
from providers.database import DatabaseManager


@pytest.fixture(autouse=True)
def reset_db_manager_fixture():
    """Ensures the DatabaseManager engine is released before and after each test."""
    DatabaseManager.release_engine()
    yield
    DatabaseManager.release_engine()


def test_database_manager_is_singleton():
    """Tests that DatabaseManager follows the Singleton pattern for its instances."""
    instance1 = DatabaseManager()
    instance2 = DatabaseManager()
    assert instance1 is instance2


@patch("providers.database.DatabaseManager._create_engine")
def test_get_engine_creates_engine_once(mock_create_engine):
    """Tests that get_engine creates the engine only on the first call."""
    engine1 = DatabaseManager.get_engine()
    engine2 = DatabaseManager.get_engine()

    assert engine1 is engine2
    mock_create_engine.assert_called_once()


@patch("providers.database.create_engine")
def test_create_engine_with_schema(mock_create_engine):
    """Tests that _create_engine creates a URL with schema if the config has it."""
    config_with_schema = Config(POSTGRES_DB_SCHEMA="test_schema_for_sure")
    DatabaseManager._create_engine(config_with_schema)

    mock_create_engine.assert_called_once()
    _, kwargs = mock_create_engine.call_args
    assert "connect_args" in kwargs
    assert "options" in kwargs["connect_args"]
    assert "search_path=test_schema_for_sure" in kwargs["connect_args"]["options"]


@patch("providers.database.create_engine")
def test_create_engine_without_schema(mock_create_engine):
    """Tests that _create_engine creates a URL without schema if config doesn't have it."""
    config_without_schema = Config(POSTGRES_DB_SCHEMA=None)
    DatabaseManager._create_engine(config_without_schema)

    mock_create_engine.assert_called_once()
    _, kwargs = mock_create_engine.call_args
    assert "options" not in kwargs.get("connect_args", {})


@patch("providers.database.create_engine")
def test_release_engine_works(mock_create_engine):
    """Tests that release_engine allows for a new engine to be created."""
    mock_create_engine.side_effect = lambda *args, **kwargs: MagicMock()

    engine1 = DatabaseManager.get_engine()
    DatabaseManager.release_engine()
    engine2 = DatabaseManager.get_engine()

    assert engine1 is not engine2
    assert mock_create_engine.call_count == 2
