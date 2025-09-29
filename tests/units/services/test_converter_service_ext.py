from unittest.mock import MagicMock, patch

import pytest
from public_detective.services.converter import ConverterService


@pytest.fixture
def converter_service() -> ConverterService:
    """Provides a ConverterService instance."""
    return ConverterService()


@patch("imageio.get_reader")
def test_gif_to_mp4_conversion_failure(mock_get_reader: MagicMock, converter_service: ConverterService) -> None:
    """Tests that an exception during GIF to MP4 conversion is handled."""
    mock_get_reader.side_effect = Exception("imageio error")
    with pytest.raises(Exception, match="imageio error"):
        converter_service.gif_to_mp4(b"bad gif content")


@patch("PIL.Image.open")
def test_bmp_to_png_conversion_failure(mock_image_open: MagicMock, converter_service: ConverterService) -> None:
    """Tests that an exception during BMP to PNG conversion is handled."""
    mock_image_open.side_effect = Exception("PIL error")
    with pytest.raises(Exception, match="PIL error"):
        converter_service.bmp_to_png(b"bad bmp content")


@patch("xlrd.open_workbook")
def test_spreadsheet_to_csvs_xls_failure(mock_open_workbook: MagicMock, converter_service: ConverterService) -> None:
    """Tests that an exception during XLS to CSV conversion is handled."""
    mock_open_workbook.side_effect = Exception("xlrd error")
    with pytest.raises(Exception, match="xlrd error"):
        converter_service.spreadsheet_to_csvs(b"bad xls content", ".xls")


@patch("openpyxl.load_workbook")
def test_spreadsheet_to_csvs_xlsx_failure(mock_load_workbook: MagicMock, converter_service: ConverterService) -> None:
    """Tests that an exception during XLSX to CSV conversion is handled."""
    mock_load_workbook.side_effect = Exception("openpyxl error")
    with pytest.raises(Exception, match="openpyxl error"):
        converter_service.spreadsheet_to_csvs(b"bad xlsx content", ".xlsx")


@patch("source.public_detective.services.converter.pyxlsb.open_workbook")
def test_spreadsheet_to_csvs_xlsb_failure(mock_open_workbook: MagicMock, converter_service: ConverterService) -> None:
    """Tests that an exception during XLSB to CSV conversion is handled."""
    mock_open_workbook.side_effect = Exception("pyxlsb error")
    with pytest.raises(Exception, match="pyxlsb error"):
        converter_service.spreadsheet_to_csvs(b"bad xlsb content", ".xlsb")
