import io
import os
import sys

import google.generativeai as genai
import psycopg2
import requests
from dotenv import load_dotenv
from google.ai import generativelanguage as glm
from models.analysis import Analysis, RedFlagCategory


def get_gcs_url_from_db(control_number: str) -> str | None:
    """
    Connects to the database and retrieves the GCS URL for a given procurement.
    """
    print(f"A procurar no banco de dados pela URL do GCS para: {control_number}")
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT"),
        )
        cursor = conn.cursor()

        # ASSUMINDO que a sua tabela se chama 'procurement_analysis' e a
        # coluna 'gcs_document_url'. Ajuste se os nomes forem diferentes.
        sql_query = """
            SELECT gcs_document_url
            FROM procurement_analysis
            WHERE procurement_control_number = %s
            ORDER BY created_at DESC
            LIMIT 1;
        """
        cursor.execute(sql_query, (control_number,))
        result = cursor.fetchone()

        cursor.close()

        if result:
            print(f"  URL encontrada: {result[0]}")
            return str(result[0])
        else:
            print("  Nenhum registo encontrado para esta licitação.")
            return None
    except psycopg2.Error as e:
        print(f"  Erro de banco de dados: {e}")
        return None
    finally:
        if conn:
            conn.close()


def download_file_from_url(url: str) -> bytes | None:
    """
    Downloads the content of a file from a given URL.
    """
    print(f"A descarregar ficheiro de: {url}")
    try:
        response = requests.get(url, timeout=90)
        response.raise_for_status()
        print(f"  Descarregado com sucesso ({len(response.content)} bytes).")
        return response.content
    except requests.RequestException as e:
        print(f"  Falha ao descarregar o ficheiro: {e}")
        return None


def analyze_file_content(file_content: bytes, file_name: str) -> None:
    """
    Uploads the file content to the Gemini API and prints the analysis.
    """
    api_key = os.getenv("GCP_GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-pro-latest")

    print("\nA carregar ficheiro para a API do Gemini...")
    uploaded_file = None
    try:
        uploaded_file = genai.upload_file(
            path=io.BytesIO(file_content),
            display_name=file_name,
            mime_type="application/zip",
        )
        print(f"  Ficheiro carregado como: {uploaded_file.name}")

        prompt = """
        Você é um auditor sénior especializado em contratações públicas no Brasil.
        A sua tarefa é analisar os documentos contidos no arquivo ZIP em anexo
        para identificar potenciais irregularidades.

        Analise todos os ficheiros e responda com um objeto JSON que siga
        estritamente o esquema fornecido, identificando irregularidades nas
        categorias: DIRECTING, COMPETITION_RESTRICTION, OVERPRICE.
        """

        compatible_schema = glm.Schema(
            type=glm.Type.OBJECT,
            properties={
                "risk_score": glm.Schema(type=glm.Type.INTEGER),
                "summary": glm.Schema(type=glm.Type.STRING),
                "red_flags": glm.Schema(
                    type=glm.Type.ARRAY,
                    items=glm.Schema(
                        type=glm.Type.OBJECT,
                        properties={
                            "category": glm.Schema(
                                type=glm.Type.STRING,
                                enum=[e.value for e in RedFlagCategory],
                            ),
                            "description": glm.Schema(type=glm.Type.STRING),
                            "evidence_quote": glm.Schema(type=glm.Type.STRING),
                            "auditor_reasoning": glm.Schema(type=glm.Type.STRING),
                        },
                        required=[
                            "category",
                            "description",
                            "evidence_quote",
                            "auditor_reasoning",
                        ],
                    ),
                ),
            },
            required=["risk_score", "summary", "red_flags"],
        )

        print("\nA enviar para análise da IA...")
        response = model.generate_content(
            [prompt, uploaded_file],
            generation_config=genai.types.GenerationConfig(
                response_schema=compatible_schema,
            ),
        )

        print("\n--- INÍCIO DA ANÁLISE DA IA ---")
        analysis_result = Analysis.model_validate(response.candidates[0].content.parts[0].function_call.args)
        print(analysis_result.model_dump_json(indent=2))
        print("--- FIM DA ANÁLISE DA IA ---")

    except Exception as e:
        print(f"\nOcorreu um erro durante a análise da IA: {e}")
    finally:
        if uploaded_file:
            print(f"\n  A apagar ficheiro carregado: {uploaded_file.name}")
            genai.delete_file(uploaded_file.name)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Uso: python test_analysis_from_db.py "<procurement_control_number>"')
        sys.exit(1)

    load_dotenv()

    control_number_arg = sys.argv[1]

    gcs_url = get_gcs_url_from_db(control_number_arg)

    if gcs_url:
        file_content = download_file_from_url(gcs_url)
        if file_content:
            file_name_for_api = f"{control_number_arg.replace('/', '_')}.zip"
            analyze_file_content(file_content, file_name_for_api)
