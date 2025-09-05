import os

import pytest

from source.models.analyses import Analysis
from source.providers.ai import AiProvider


@pytest.fixture(scope="module")
def vertex_ai_auth():
    """
    Fixture to handle authentication for Vertex AI tests.
    It checks for the necessary environment variables and skips the test if not found.
    """
    if not os.getenv("GCP_PROJECT") or not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        pytest.skip("GCP_PROJECT or GOOGLE_APPLICATION_CREDENTIALS not set, skipping e2e test.")
    yield


@pytest.mark.e2e
def test_vertex_ai_e2e_flow(vertex_ai_auth):  # noqa: F841
    """
    Tests a full end-to-end flow using the AiProvider to make a real
    call to the Vertex AI API.
    """
    # Arrange
    ai_provider = AiProvider(Analysis)

    # A simple prompt that asks the model to act as a procurement auditor
    prompt = """
    Você é um auditor sênior especializado em licitações públicas no Brasil.
    Sua tarefa é analisar o documento em anexo para identificar
    possíveis irregularidades no processo de licitação.
    O documento é um edital simples. Analise e retorne um score de risco de 0 a 10.
    """

    # Create a dummy PDF file in memory
    # This content is simple but represents a real file being sent.
    pdf_content = (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n"
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 52 >>\nstream\nBT\n"
        b"/F1 24 Tf\n100 700 Td\n(Hello, World!) Tj\nET\nendstream\nendobj\nxref\n"
        b"0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
        b"0000000111 00000 n \n0000000198 00000 n \ntrailer\n"
        b"<< /Size 5 /Root 1 0 R >>\nstartxref\n289\n%%EOF"
    )
    files = [("dummy_document.pdf", pdf_content)]

    # Act
    # This will make a real call to the Vertex AI API.
    # The `vertex_ai_auth` fixture ensures this test only runs if credentials are set.
    analysis_result, input_tokens, output_tokens = ai_provider.get_structured_analysis(
        prompt=prompt,
        files=files,
        max_output_tokens=1024,  # Set a reasonable token limit for the test
    )

    # Assert
    # The primary goal is to ensure the API call succeeds and returns a valid,
    # Pydantic-validated object. We don't need to assert the content, just the structure.
    assert isinstance(analysis_result, Analysis)
    assert isinstance(analysis_result.risk_score, int)
    assert 0 <= analysis_result.risk_score <= 10
    assert analysis_result.procurement_summary is not None
    assert analysis_result.risk_score_rationale is not None

    print("E2E test successful!")
    print(f"Input tokens: {input_tokens}, Output tokens: {output_tokens}")
    print(f"Risk Score: {analysis_result.risk_score}")
    print(f"Summary: {analysis_result.procurement_summary}")
