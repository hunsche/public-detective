"""
Integration tests for the full analysis pipeline.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from models.procurement import Procurement
from services.analysis import AnalysisService
from alembic.config import Config
from alembic import command


@pytest.fixture(scope="session", autouse=True)
def run_migrations(monkeypatch):
    """
    Runs alembic migrations on the test database before any tests are run.
    """
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_DB", "public_detective")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.mark.integration
@patch("providers.converter.which", return_value="/usr/bin/libreoffice")
@patch("subprocess.run")
@patch("services.analysis.AiProvider")
@patch("services.analysis.ProcurementRepository")
def test_full_analysis_and_idempotency(
    mock_proc_repo, mock_ai_provider, mock_subprocess, mock_which, monkeypatch
):
    """
    Tests the full analysis flow, including saving to the database
    and the idempotency check on a second run.
    """
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")

    file_content = b"This is a test document."
    ai_response = MagicMock()
    ai_response.risk_score = 7
    ai_response.risk_score_rationale = "High risk detected."
    ai_response.summary = "This is a summary."
    ai_response.red_flags = []

    mock_proc_repo.return_value.process_procurement_documents.return_value = (
        [("test.docx", file_content)], [("test.docx", file_content)]
    )
    mock_ai_provider.return_value.convert_files.return_value = [("test.docx.pdf", file_content)]
    mock_ai_provider.return_value.get_structured_analysis.return_value = ai_response

    mock_subprocess_result = MagicMock()
    mock_subprocess_result.returncode = 0
    mock_subprocess.return_value = mock_subprocess_result

    service = AnalysisService()
    procurement = Procurement(
        pncp_control_number="integration-test-123", year=2025, mode="test",
        status="test", object="test", url="http://test.com"
    )

    # First run
    service.analyze_procurement(procurement)

    # Assertions for First Run
    service.analysis_repo.save_analysis.assert_called_once()
    saved_result = service.analysis_repo.save_analysis.call_args[0][0]

    # Second run should be idempotent
    service.analysis_repo.get_analysis_by_hash.return_value = saved_result
    service.analyze_procurement(procurement)

    # Assert that save was not called again
    service.analysis_repo.save_analysis.assert_called_once()
