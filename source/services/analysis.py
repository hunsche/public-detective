"""
This module defines the service responsible for orchestrating the procurement
analysis pipeline.
"""
import hashlib
import io
import zipfile
from datetime import date, timedelta
from typing import List, Tuple

from models.analysis import Analysis, AnalysisResult
from models.procurement import Procurement
from providers.ai import AiProvider
from providers.config import Config, ConfigProvider
from providers.gcs import GcsProvider
from providers.logging import Logger, LoggingProvider
from repositories.analysis import AnalysisRepository
from repositories.procurement import ProcurementRepository


class AnalysisService:
    """
    Orchestrates the analysis of individual procurements.
    """

    _SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc", ".rtf", ".xlsx", ".xls", ".csv")
    _FILE_PRIORITY_ORDER = [
        "edital", "termo de referencia", "projeto basico", "planilha",
        "orcamento", "custos", "contrato", "ata de registro"
    ]
    _MAX_FILES_FOR_AI = 10
    _MAX_SIZE_BYTES_FOR_AI = 20 * 1024 * 1024

    def __init__(self) -> None:
        """Initializes the service and its dependencies."""
        self.procurement_repo = ProcurementRepository()
        self.analysis_repo = AnalysisRepository()
        self.logger = LoggingProvider.get_logger()
        self.ai_provider = AiProvider(Analysis)
        self.gcs_provider = GcsProvider()
        self.config = ConfigProvider.get_config()

    def analyze_procurement(self, procurement: Procurement) -> None:
        """
        Executes the full analysis pipeline for a single procurement.
        """
        control_number = procurement.pncp_control_number
        self.logger.info(f"Starting analysis for procurement {control_number}...")

        _, all_original_files = self.procurement_repo.process_procurement_documents(procurement)

        if not all_original_files:
            self.logger.warning(f"No files found for {control_number}. Aborting.")
            return

        files_for_ai, warnings = self._select_and_prepare_files_for_ai(all_original_files)

        if not files_for_ai:
            self.logger.error(f"No supported files left after filtering for {control_number}.")
            return

        document_hash = self._calculate_hash(files_for_ai)
        if self.analysis_repo.get_analysis_by_hash(document_hash):
            self.logger.info(f"Analysis for hash {document_hash} already exists. Skipping.")
            return

        try:
            processed_files = self.ai_provider.convert_files(files_for_ai)

            original_zip_url = self._archive_and_upload(
                f"{control_number}-original.zip", all_original_files
            )
            processed_zip_url = self._archive_and_upload(
                f"{control_number}-processed.zip", processed_files
            )

            prompt = self._build_analysis_prompt(procurement, warnings)
            ai_analysis = self.ai_provider.get_structured_analysis(
                prompt=prompt,
                files=processed_files,
            )

            final_result = AnalysisResult(
                procurement_control_number=control_number,
                ai_analysis=ai_analysis,
                warnings=warnings,
                document_hash=document_hash,
                original_documents_url=original_zip_url,
                processed_documents_url=processed_zip_url,
            )
            self.analysis_repo.save_analysis(final_result)
            self.logger.info(f"Successfully completed analysis for {control_number}.")

        except Exception as e:
            self.logger.error(f"Analysis pipeline failed for {control_number}: {e}", exc_info=True)
            raise

    def _calculate_hash(self, files: list[tuple[str, bytes]]) -> str:
        """Calculates a SHA-256 hash from the content of a list of files."""
        hasher = hashlib.sha256()
        for _, content in sorted(files, key=lambda x: x[0]):
            hasher.update(content)
        return hasher.hexdigest()

    def _archive_and_upload(self, zip_name: str, files: list[tuple[str, bytes]]) -> str:
        """Creates a zip archive from a list of files and uploads it to GCS."""
        self.logger.info(f"Creating and uploading archive: {zip_name}")
        with io.BytesIO() as zip_buffer:
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for filename, content in files:
                    zf.writestr(filename, content)
            zip_content = zip_buffer.getvalue()

        return self.gcs_provider.upload_file(
            bucket_name=self.gcs_provider.config.GCP_GCS_BUCKET_PROCUREMENTS,
            destination_blob_name=zip_name,
            content=zip_content,
            content_type="application/zip",
        )

    def _select_and_prepare_files_for_ai(
        self, all_files: list[tuple[str, bytes]]
    ) -> tuple[list[tuple[str, bytes]], list[str]]:
        """
        Applies business rules to filter, prioritize, and limit files for AI analysis.
        """
        warnings = []
        supported_files = [
            (path, content)
            for path, content in all_files
            if path.lower().endswith(self._SUPPORTED_EXTENSIONS)
        ]

        supported_files.sort(key=lambda item: self._get_priority(item[0]))

        selected_files = supported_files
        if len(supported_files) > self._MAX_FILES_FOR_AI:
            excluded_by_count = [path for path, _ in supported_files[self._MAX_FILES_FOR_AI:]]
            warnings.append(
                f"Limite de arquivos excedido. Os seguintes arquivos foram ignorados: {', '.join(excluded_by_count)}"
            )
            selected_files = supported_files[:self._MAX_FILES_FOR_AI]

        final_files, excluded_by_size = [], []
        current_size = 0
        for path, content in selected_files:
            if current_size + len(content) > self._MAX_SIZE_BYTES_FOR_AI:
                excluded_by_size.append(path)
            else:
                final_files.append((path, content))
                current_size += len(content)

        if excluded_by_size:
            warnings.append(
                f"O limite de tamanho total de {self._MAX_SIZE_BYTES_FOR_AI / 1024 / 1024:.1f}MB foi excedido. "
                f"Os seguintes arquivos foram ignorados: {', '.join(excluded_by_size)}"
            )

        for warning_msg in warnings:
            self.logger.warning(warning_msg)

        return final_files, warnings

    def _get_priority(self, file_path: str) -> int:
        """Determines the priority of a file based on keywords in its name."""
        path_lower = file_path.lower()
        for i, keyword in enumerate(self._FILE_PRIORITY_ORDER):
            if keyword in path_lower:
                return i
        return len(self._FILE_PRIORITY_ORDER)

    def _build_analysis_prompt(
        self, procurement: Procurement, warnings: list[str]
    ) -> str:
        """Constructs the prompt for the AI, including contextual warnings."""
        procurement_json = procurement.model_dump_json(by_alias=True, indent=2)
        warnings_section = ""
        if warnings:
            warnings_text = "\n- ".join(warnings)
            warnings_section = f"""
            --- ATENÇÃO ---
            Os seguintes problemas foram detectados ao preparar os arquivos.
            Considere estas limitações em sua análise:
            - {warnings_text}
            --- FIM DOS AVISOS ---
            """

        return f"""
        Você é um auditor sênior especializado em licitações públicas no Brasil.
        Sua tarefa é analisar os documentos em anexo para identificar
        possíveis irregularidades no processo de licitação.
        {warnings_section}
        Primeiro, revise os metadados da licitação em formato JSON para obter o contexto.
        Em seguida, inspecione todos os arquivos anexados.

        --- METADADOS DA LICITAÇÃO (JSON) ---
        {procurement_json}
        --- FIM DOS METADADOS ---

        Com base em todas as informações disponíveis, analise a licitação em
        busca de irregularidades nas seguintes categorias. Para cada achado, você deve
        extrair a citação exata de um dos documentos que embase sua análise.

        1.  Direcionamento para Fornecedor Específico (DIRECIONAMENTO)
        2.  Restrição de Competitividade (RESTRICAO_COMPETITIVIDADE)
        3.  Potencial de Sobrepreço (SOBREPRECO)

        Após a análise, atribua uma nota de risco de 0 a 10 e forneça uma justificativa detalhada para essa nota (em pt-br).

        **Critérios para a Nota de Risco:**
        - **0-2 (Risco Baixo):** Nenhuma irregularidade significativa encontrada.
        - **3-5 (Risco Moderado):** Foram encontrados indícios de irregularidades, mas sem evidências conclusivas.
        - **6-8 (Risco Alto):** Evidências claras de irregularidades em uma ou mais categorias.
        - **9-10 (Risco Crítico):** Irregularidades graves e generalizadas, com forte suspeita de fraude.

        Sua resposta deve ser um objeto JSON que siga estritamente o esquema fornecido, incluindo o campo `risk_score_rationale`.
        """

    def run_analysis(self, start_date: date, end_date: date):
        """
        Runs the Public Detective analysis job for the specified date range.
        """
        self.logger.info(f"Starting analysis job for date range: {start_date} to {end_date}")
        current_date = start_date
        while current_date <= end_date:
            self.logger.info(f"Processing date: {current_date}")
            updated_procurements = self.procurement_repo.get_updated_procurements(target_date=current_date)

            if not updated_procurements:
                self.logger.info(f"No procurements were updated on {current_date}. Moving to next day.")
                current_date += timedelta(days=1)
                continue

            self.logger.info(f"Found {len(updated_procurements)} updated procurements. Publishing to message queue.")
            success_count, failure_count = 0, 0
            for procurement in updated_procurements:
                published = self.procurement_repo.publish_procurement_to_pubsub(procurement)
                if published:
                    success_count += 1
                else:
                    failure_count += 1
            self.logger.info(f"Finished processing for {current_date}. Success: {success_count}, Failures: {failure_count}")
            current_date += timedelta(days=1)
        self.logger.info("Analysis job for the entire date range has been completed.")
