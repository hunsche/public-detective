"""This module contains unit tests for the ConverterService."""

import pytest
from public_detective.services.converter import ConverterService


@pytest.fixture
def converter_service() -> ConverterService:
    """Returns a ConverterService instance for testing."""
    return ConverterService()


def test_is_supported_for_conversion_supported(
    converter_service: ConverterService,
) -> None:
    """Tests that a supported extension is correctly identified."""
    assert converter_service.is_supported_for_conversion(".docx") is True


def test_is_supported_for_conversion_unsupported(
    converter_service: ConverterService,
) -> None:
    """Tests that an unsupported extension is correctly identified."""
    assert converter_service.is_supported_for_conversion(".xyz") is False
