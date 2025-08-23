import os
from unittest.mock import patch

import pytest
from models.procurement import Procurement
from services.analysis import AnalysisService


@pytest.mark.integration
@patch("providers.converter.which", return_value="/usr/bin/libreoffice")
@patch("subprocess.run")
def test_full_analysis_flow(mock_subprocess_run, mock_which, monkeypatch):
    """
    Tests the full analysis flow from procurement to database persistence.
    This test requires the Docker services to be running.
    """
    # Set environment variables for the test database
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_DB", "public_detective")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")

    # Mock the AI provider to return a fixed analysis
    with patch("services.analysis.AiProvider") as mock_ai_provider:
        mock_ai_instance = mock_ai_provider.return_value
        mock_ai_instance.get_structured_analysis.return_value = {
            "risk_score": 5,
            "risk_score_rationale": "Rationale",
            "summary": "Summary",
            "red_flags": [],
        }

        # Mock the procurement repository to return a dummy procurement
        with patch("services.analysis.ProcurementRepository") as mock_proc_repo:
            mock_proc_repo.return_value.process_procurement_documents.return_value = (
                [("file.pdf", b"content")],
                [("file.pdf", b"content")],
            )

            service = AnalysisService()
            procurement = Procurement(
                pncp_control_number="12345",
                year=2025,
                mode="Pregão",
                status="Aberto",
                object="Test object",
                url="http://test.com",
            )

            # First run: should perform analysis and save to DB
            service.analyze_procurement(procurement)

            # Second run: should be idempotent and skip analysis
            service.analyze_procurement(procurement)

            # Assertions
            mock_ai_instance.get_structured_analysis.assert_called_once()
            # Further assertions would require a real DB connection to check the content.
            # This test mainly ensures the flow runs without errors.
            assert service.analysis_repo.get_analysis_by_hash.call_count == 2
