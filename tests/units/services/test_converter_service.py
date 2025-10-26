"""Unit tests for the ConverterService."""

from unittest.mock import ANY, MagicMock, patch

import pytest
from public_detective.services.converter import ConverterService


@pytest.fixture
def converter_service() -> ConverterService:
    """Provides a ConverterService instance for testing."""
    return ConverterService()


@patch("imageio.get_reader")
@patch("imageio.get_writer")
def test_gif_to_mp4(
    mock_get_writer: MagicMock, mock_get_reader: MagicMock, converter_service: ConverterService
) -> None:
    """Test the gif_to_mp4 method successfully converts GIF to MP4."""
    dummy_gif_content = b"GIF89a..."
    mock_reader = mock_get_reader.return_value
    mock_reader.get_meta_data.return_value = {"fps": 30}
    mock_reader.__iter__.return_value = [b"frame1", b"frame2"]
    mock_writer_instance = mock_get_writer.return_value.__enter__.return_value

    result = converter_service.gif_to_mp4(dummy_gif_content)

    mock_get_reader.assert_called_once_with(dummy_gif_content, format="gif")
    mock_get_writer.assert_called_once()
    assert mock_writer_instance.append_data.call_count == 2
    assert isinstance(result, bytes)


@patch("PIL.Image.open")
def test_bmp_to_png(mock_open: MagicMock, converter_service: ConverterService) -> None:
    """Test the bmp_to_png method successfully converts BMP to PNG."""
    dummy_bmp_content = b"BM..."
    mock_img = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_img

    result = converter_service.bmp_to_png(dummy_bmp_content)

    mock_img.save.assert_called_once_with(ANY, format="PNG")
    assert isinstance(result, bytes)


@patch("imageio.get_reader")
def test_gif_to_mp4_conversion_failure(mock_get_reader: MagicMock, converter_service: ConverterService) -> None:
    """Tests that an exception during GIF to MP4 conversion is properly handled."""
    mock_get_reader.side_effect = Exception("imageio error")
    with pytest.raises(Exception, match="imageio error"):
        converter_service.gif_to_mp4(b"bad gif content")


@patch("PIL.Image.open")
def test_bmp_to_png_conversion_failure(mock_image_open: MagicMock, converter_service: ConverterService) -> None:
    """Tests that an exception during BMP to PNG conversion is properly handled."""
    mock_image_open.side_effect = Exception("PIL error")
    with pytest.raises(Exception, match="PIL error"):
        converter_service.bmp_to_png(b"bad bmp content")


@patch("public_detective.providers.office_converter.OfficeConverterProvider.to_pdf")
def test_convert_to_pdf(mock_to_pdf: MagicMock, converter_service: ConverterService) -> None:
    """Tests the main convert_to_pdf method, ensuring it calls the provider."""
    mock_to_pdf.return_value = b"pdf content"
    result = converter_service.convert_to_pdf(b"test content", ".test")
    assert result == b"pdf content"
    mock_to_pdf.assert_called_once_with(b"test content", ".test")


@patch("public_detective.services.converter.ConverterService.convert_to_pdf")
def test_doc_to_pdf(mock_convert_to_pdf: MagicMock, converter_service: ConverterService) -> None:
    """Tests the doc_to_pdf method delegates correctly."""
    mock_convert_to_pdf.return_value = b"pdf content"
    result = converter_service.doc_to_pdf(b"doc content")
    assert result == b"pdf content"
    mock_convert_to_pdf.assert_called_once_with(b"doc content", ".doc")


@patch("public_detective.services.converter.ConverterService.convert_to_pdf")
def test_docx_to_pdf(mock_convert_to_pdf: MagicMock, converter_service: ConverterService) -> None:
    """Tests the docx_to_pdf method delegates correctly."""
    mock_convert_to_pdf.return_value = b"pdf content"
    result = converter_service.docx_to_pdf(b"docx content")
    assert result == b"pdf content"
    mock_convert_to_pdf.assert_called_once_with(b"docx content", ".docx")


@patch("public_detective.services.converter.ConverterService.convert_to_pdf")
def test_rtf_to_pdf(mock_convert_to_pdf: MagicMock, converter_service: ConverterService) -> None:
    """Tests the rtf_to_pdf method delegates correctly."""
    mock_convert_to_pdf.return_value = b"pdf content"
    result = converter_service.rtf_to_pdf(b"rtf content")
    assert result == b"pdf content"
    mock_convert_to_pdf.assert_called_once_with(b"rtf content", ".rtf")


@patch("public_detective.services.converter.ConverterService.convert_to_pdf")
def test_xls_to_pdf(mock_convert_to_pdf: MagicMock, converter_service: ConverterService) -> None:
    """Tests the xls_to_pdf method delegates correctly."""
    mock_convert_to_pdf.return_value = b"pdf content"
    result = converter_service.xls_to_pdf(b"xls content")
    assert result == b"pdf content"
    mock_convert_to_pdf.assert_called_once_with(b"xls content", ".xls")


@patch("public_detective.services.converter.ConverterService.convert_to_pdf")
def test_xlsx_to_pdf(mock_convert_to_pdf: MagicMock, converter_service: ConverterService) -> None:
    """Tests the xlsx_to_pdf method delegates correctly."""
    mock_convert_to_pdf.return_value = b"pdf content"
    result = converter_service.xlsx_to_pdf(b"xlsx content")
    assert result == b"pdf content"
    mock_convert_to_pdf.assert_called_once_with(b"xlsx content", ".xlsx")


@patch("public_detective.services.converter.ConverterService.convert_to_pdf")
def test_xlsb_to_pdf(mock_convert_to_pdf: MagicMock, converter_service: ConverterService) -> None:
    """Tests the xlsb_to_pdf method delegates correctly."""
    mock_convert_to_pdf.return_value = b"pdf content"
    result = converter_service.xlsb_to_pdf(b"xlsb content")
    assert result == b"pdf content"
    mock_convert_to_pdf.assert_called_once_with(b"xlsb content", ".xlsb")
