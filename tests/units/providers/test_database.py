from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from providers.database import DatabaseManager


@pytest.fixture(autouse=True)
def reset_db_manager() -> Generator[None, None, None]:
    """Ensures the DatabaseManager is reset before each test.

    Yields:
        None.
    """
    DatabaseManager.release_engine()
    yield
    DatabaseManager.release_engine()


def test_singleton_behavior() -> None:
    """Tests that DatabaseManager is a singleton."""
    instance1 = DatabaseManager()
    instance2 = DatabaseManager()
    assert instance1 is instance2


@patch("providers.database.create_engine")
def test_get_engine_creates_once(mock_create_engine: MagicMock) -> None:
    """Tests that the engine is created only once.

    Args:
        mock_create_engine: Mock for sqlalchemy.create_engine.
    """
    engine1 = DatabaseManager.get_engine()
    engine2 = DatabaseManager.get_engine()

    assert engine1 is engine2
    mock_create_engine.assert_called_once()


@patch("providers.database.create_engine")
def test_get_engine_with_schema(mock_create_engine: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that the engine is created with schema options if specified.

    Args:
        mock_create_engine: Mock for sqlalchemy.create_engine.
        monkeypatch: Pytest fixture for mocking.
    """
    monkeypatch.setenv("POSTGRES_DB_SCHEMA", "test_schema")
    DatabaseManager.get_engine()

    mock_create_engine.assert_called_once()
    _, kwargs = mock_create_engine.call_args
    assert "options" in kwargs["connect_args"]
    assert "search_path=test_schema" in kwargs["connect_args"]["options"]


def test_release_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that the engine can be released.

    Args:
        monkeypatch: Pytest fixture for mocking.
    """
    monkeypatch.setenv("POSTGRES_DB_SCHEMA", "test_schema")
    engine1 = DatabaseManager.get_engine()
    DatabaseManager.release_engine()
    engine2 = DatabaseManager.get_engine()

    assert engine1 is not engine2
