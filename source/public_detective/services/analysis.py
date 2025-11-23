"""This module defines the core service for handling procurement analyses."""

import hashlib
import json
import os
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import AnalysisResult, GroundingMetadata, GroundingSource
from public_detective.models.candidates import AIFileCandidate
from public_detective.models.file_records import ExclusionReason, NewFileRecord, PrioritizationLogic
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.models.source_documents import NewSourceDocument
from public_detective.providers.ai import AiProvider
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.file_type import SPECIALIZED_IMAGE, FileTypeProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.http import HttpProvider
from public_detective.providers.image_converter import ImageConverterProvider
from public_detective.providers.logging import Logger, LoggingProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledgers import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcessedFile, ProcurementsRepository
from public_detective.repositories.source_documents import SourceDocumentsRepository
from public_detective.repositories.status_histories import StatusHistoryRepository
from public_detective.services.converter import ConverterService
from public_detective.services.pricing import Modality, PricingService
from public_detective.services.ranking import RankingService


class AnalysisService:
    """Orchestrates the entire procurement analysis pipeline."""

    procurement_repo: ProcurementsRepository
    analysis_repo: AnalysisRepository
    source_document_repo: SourceDocumentsRepository
    file_record_repo: FileRecordsRepository
    status_history_repo: StatusHistoryRepository
    budget_ledger_repo: BudgetLedgerRepository
    ai_provider: AiProvider
    gcs_provider: GcsProvider
    http_provider: HttpProvider
    converter_service: ConverterService
    pubsub_provider: PubSubProvider | None
    logger: Logger
    config: Config
    pricing_service: PricingService

    _SUPPORTED_EXTENSIONS = (
        ".pdf",
        ".docx",
        ".doc",
        ".odt",
        ".rtf",
        ".xlsx",
        ".xls",
        ".xlsb",
        ".ods",
        ".csv",
        ".txt",
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".mp3",
        ".wav",
        ".flac",
        ".ogg",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".html",
        ".xml",
        ".json",
        ".md",
        ".pptx",
        ".xlsm",
        ".docm",
        ".log",
        ".htm",
        ".jfif",
        ".odg",
        ".tif",
    )
    _VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv")
    _AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg")
    _IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp")
    _SPECIALIZED_IMAGE_EXTENSIONS = (".ai", ".psd", ".eps", ".cdr")
    _SPREADSHEET_EXTENSIONS = (".xlsx", ".xls", ".xlsb", ".ods")
    _FILE_PRIORITY_ORDER = [
        "edital",
        "termo de referencia",
        "projeto basico",
        "planilha",
        "orcamento",
        "custos",
        "contrato",
        "ata de registro",
    ]

    def __init__(
        self,
        procurement_repo: ProcurementsRepository,
        analysis_repo: AnalysisRepository,
        source_document_repo: SourceDocumentsRepository,
        file_record_repo: FileRecordsRepository,
        status_history_repo: StatusHistoryRepository,
        budget_ledger_repo: BudgetLedgerRepository,
        ai_provider: AiProvider,
        gcs_provider: GcsProvider,
        http_provider: HttpProvider,
        pubsub_provider: PubSubProvider | None = None,
        gcs_path_prefix: str | None = None,
    ) -> None:
        """Initializes the service with its dependencies.

        Args:
            procurement_repo: The repository for procurement data.
            analysis_repo: The repository for analysis data.
            source_document_repo: The repository for source document data.
            file_record_repo: The repository for file record data.
            status_history_repo: The repository for status history data.
            budget_ledger_repo: The repository for budget ledger data.
            ai_provider: The provider for AI services.
            gcs_provider: The provider for Google Cloud Storage services.
            http_provider: The provider for HTTP requests.
            pubsub_provider: The provider for Pub/Sub services.
            gcs_path_prefix: Overwrites the base GCS path for uploads.
        """
        self.procurement_repo = procurement_repo
        self.analysis_repo = analysis_repo
        self.source_document_repo = source_document_repo
        self.file_record_repo = file_record_repo
        self.status_history_repo = status_history_repo
        self.budget_ledger_repo = budget_ledger_repo
        self.ai_provider = ai_provider
        self.gcs_provider = gcs_provider
        self.http_provider = http_provider
        self.converter_service = ConverterService()
        self.file_type_provider = FileTypeProvider()
        self.image_converter_provider = ImageConverterProvider()
        self.pubsub_provider = pubsub_provider
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.pricing_service = PricingService()
        self.ranking_service = RankingService(
            analysis_repo=self.analysis_repo, pricing_service=self.pricing_service, config=self.config
        )
        self.gcs_path_prefix = gcs_path_prefix

    def _get_modality_from_exts(self, extensions: list[str | None]) -> Modality:
        """Determines the modality of an analysis based on file extensions.

        Args:
            extensions: A list of file extensions.

        Returns:
            The modality of the analysis.
        """
        for ext in extensions:
            if not ext:
                continue
            ext = "." + ext.lower()
            if ext in self._VIDEO_EXTENSIONS:
                return Modality.VIDEO
            if ext in self._AUDIO_EXTENSIONS:
                return Modality.AUDIO
            if ext in self._IMAGE_EXTENSIONS:
                return Modality.IMAGE
        return Modality.TEXT

    def _update_status_with_history(
        self,
        analysis_id: UUID,
        status: ProcurementAnalysisStatus,
        details: str | None = None,
    ) -> None:
        """Updates the analysis status and records the change in the history table.

        Args:
            analysis_id: The ID of the analysis to update.
            status: The new status of the analysis.
            details: Additional details about the status change.
        """
        self.analysis_repo.update_analysis_status(analysis_id, status)
        self.status_history_repo.create_record(analysis_id, status, details)

    def process_analysis_from_message(self, analysis_id: UUID, max_output_tokens: int | None = None) -> None:
        """Processes a single analysis request received from a message queue.

        Args:
            analysis_id: The ID of the analysis to process.
            max_output_tokens: The maximum number of output tokens for the AI model.
        """
        try:
            analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
            if not analysis:
                self.logger.error(f"Analysis with ID {analysis_id} not found.")
                return

            analysis_record = self.analysis_repo.get_analysis_by_id(analysis_id)
            if not analysis_record:
                raise AnalysisError(f"Analysis record {analysis_id} not found.")

            procurement = self.procurement_repo.get_procurement_by_id_and_version(
                analysis.procurement_control_number, analysis.version_number
            )
            if not procurement:
                self.logger.error(
                    f"Procurement {analysis.procurement_control_number} version {analysis.version_number} not found."
                )
                return

            try:
                self.analyze_procurement(procurement, analysis.version_number, analysis_id, max_output_tokens)
                self._update_status_with_history(
                    analysis_id, ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL, "Analysis completed successfully."
                )
            except Exception as e:
                self.logger.error(f"Analysis pipeline failed for analysis {analysis_id}: {e}", exc_info=True)
                self._update_status_with_history(analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED, str(e))
                raise
        except Exception as e:
            raise AnalysisError(f"Failed to process analysis from message: {e}") from e

    def _resolve_redirects(self, url: str) -> str:
        """Resolves redirects for a given URL to find the final destination.

        Uses a simple heuristic to avoid unnecessary requests by only resolving
        URLs that appear to be tracking or redirect URLs. First attempts an
        efficient HEAD request, then falls back to GET if HEAD fails (some
        servers block HEAD requests).

        Args:
            url: The URL to resolve.

        Returns:
            The final URL after following redirects, or the original URL if
            resolution fails.
        """
        if "vertexaisearch" not in url and "google.com/url" not in url:
            return url

        try:
            self.logger.info(f"Resolving redirect for URL: {url}")
            response = self.http_provider.head(url, allow_redirects=True)
            if response.status_code < 400:
                self.logger.info(f"Resolved to: {response.url}")
                return str(response.url)

            response = self.http_provider.get(url, allow_redirects=True, stream=True)
            self.logger.info(f"Resolved (fallback GET) to: {response.url}")
            return str(response.url)
        except Exception as e:
            self.logger.warning(f"Failed to resolve URL {url}: {e}")
            return url

    def _process_grounding_metadata(self, raw_metadata: dict) -> GroundingMetadata:
        """Processes raw grounding metadata, resolving redirects in sources.

        Args:
            raw_metadata: Dict with 'search_queries' and 'sources' (list of dicts).

        Returns:
            GroundingMetadata object with resolved URLs.
        """
        raw_sources = raw_metadata.get("sources", [])
        processed_sources = []
        for source in raw_sources:
            original_url = source.get("original_url")
            if not original_url:
                continue

            resolved_url = self._resolve_redirects(original_url)
            processed_sources.append(
                GroundingSource(
                    original_url=original_url,
                    resolved_url=resolved_url if resolved_url != original_url else None,
                    title=source.get("title"),
                )
            )

        return GroundingMetadata(
            search_queries=raw_metadata.get("search_queries", []),
            sources=processed_sources,
        )

    def analyze_procurement(
        self,
        procurement: Procurement,
        version_number: int,
        analysis_id: UUID,
        max_output_tokens: int | None = None,
    ) -> None:
        """Orchestrates the analysis of a procurement.

        Args:
            procurement: The procurement object to analyze.
            version_number: The version number of the procurement data.
            analysis_id: The unique identifier for this analysis.
            max_output_tokens: Optional token limit for the AI response.

        Raises:
            AnalysisError: If any step of the analysis pipeline fails.
        """
        control_number = procurement.pncp_control_number
        self.logger.info(f"Starting analysis for procurement {control_number} (v{version_number})...")

        try:
            procurement_id = self.procurement_repo.get_procurement_uuid(procurement.pncp_control_number, version_number)
            if not procurement_id:
                self.logger.warning(
                    f"Could not find procurement UUID for {control_number} "
                    f"v{version_number}. Proceeding with analysis without documents."
                )
            file_records = self.file_record_repo.get_all_file_records_by_analysis_id(str(analysis_id))
            if not file_records:
                self.logger.warning(
                    f"No file records found for analysis {analysis_id}. Proceeding with analysis without documents."
                )

            included_records = [rec for rec in file_records if rec.get("included_in_analysis")]
            if not included_records:
                self.logger.warning(
                    f"No files were selected for analysis for {control_number}. "
                    f"Proceeding with analysis without documents."
                )

            files_for_ai_uris = [
                uri
                for rec in included_records
                if rec.get("prepared_content_gcs_uris")
                for uri in rec["prepared_content_gcs_uris"]
            ]
            if not files_for_ai_uris and included_records:
                self.logger.warning(
                    f"No prepared content URIs found for {control_number} " f"despite having included records."
                )

            candidates = []
            for rec in included_records:
                cand = AIFileCandidate(
                    synthetic_id=str(rec.get("source_document_id", "")),
                    raw_document_metadata=rec.get("raw_document_metadata") or {},
                    original_path=rec.get("original_filename", ""),
                    original_content=b"",
                    extraction_failed=False,
                )
                cand.ai_path = rec.get("ai_path") or rec.get("original_filename", "unknown_file")
                cand.prepared_content_gcs_uris = rec.get("prepared_content_gcs_uris")
                candidates.append(cand)

            prompt = self._build_analysis_prompt(procurement, candidates)

            (
                ai_analysis,
                input_tokens,
                output_tokens,
                thinking_tokens,
                raw_grounding_metadata,
                thoughts,
            ) = self.ai_provider.get_structured_analysis(
                prompt=prompt, file_uris=files_for_ai_uris, max_output_tokens=max_output_tokens
            )

            grounding_metadata = self._process_grounding_metadata(raw_grounding_metadata)

            gcs_base_path = f"{procurement_id}/{analysis_id}"

            analysis_record = self.analysis_repo.get_analysis_by_id(analysis_id)
            document_hash = analysis_record.document_hash if analysis_record else None

            final_result = AnalysisResult(
                procurement_control_number=control_number,
                version_number=version_number,
                ai_analysis=ai_analysis,
                document_hash=document_hash,
                original_documents_gcs_path=gcs_base_path,
                processed_documents_gcs_path=None,
                analysis_prompt=prompt,
                grounding_metadata=grounding_metadata,
                thoughts=thoughts,
            )

            exts = [rec.get("extension") for rec in included_records]
            modality = self._get_modality_from_exts(exts)

            search_queries_count = len(grounding_metadata.search_queries)
            (
                input_cost,
                output_cost,
                thinking_cost,
                search_cost,
                total_cost,
            ) = self.pricing_service.calculate_total_cost(
                input_tokens,
                output_tokens,
                thinking_tokens,
                modality=modality,
                search_queries_count=search_queries_count,
            )
            self.analysis_repo.save_analysis(
                analysis_id=analysis_id,
                result=final_result,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens,
                input_cost=input_cost,
                output_cost=output_cost,
                thinking_cost=thinking_cost,
                search_cost=search_cost,
                total_cost=total_cost,
                search_queries_used=search_queries_count,
            )

            self.budget_ledger_repo.save_expense(
                analysis_id,
                total_cost,
                f"Análise da licitação {procurement.pncp_control_number} (v{version_number}).",
            )

            self.logger.info(f"Successfully completed analysis for {control_number}.")

        except ValueError as e:
            self.logger.error(
                f"Analysis pipeline failed for {control_number} due to AI model error: {e}", exc_info=True
            )
            raise AnalysisError(f"AI Model Error: {e}") from e
        except Exception as e:
            self.logger.error(
                f"Analysis pipeline failed for {control_number} due to unexpected error: {e}", exc_info=True
            )
            raise AnalysisError(f"Unexpected Error: {e}") from e

    def _prepare_ai_candidates(self, all_files: list[ProcessedFile]) -> list[AIFileCandidate]:
        """Prepares a list of AIFileCandidate objects from raw file data.

        Args:
            all_files: A list of `ProcessedFile` objects from the repository.

        Returns:
            A list of AIFileCandidate objects.
        """
        candidates = []
        for processed_file in all_files:
            candidate = AIFileCandidate(
                synthetic_id=processed_file.source_document_id,
                raw_document_metadata=processed_file.raw_document_metadata,
                original_path=processed_file.relative_path,
                original_content=processed_file.content,
                extraction_failed=processed_file.extraction_failed,
            )
            ext = os.path.splitext(processed_file.relative_path)[1].lower()

            if os.path.basename(candidate.original_path).startswith("~$"):
                candidate.exclusion_reason = ExclusionReason.LOCK_FILE
                candidates.append(candidate)
                continue

            if processed_file.extraction_failed:
                candidate.exclusion_reason = ExclusionReason.EXTRACTION_FAILED
                candidates.append(candidate)
                continue

            if self.file_type_provider.get_file_type(ext) == SPECIALIZED_IMAGE:
                try:
                    converted_content = self.image_converter_provider.to_png(processed_file.content, ext)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.png"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                except Exception as e:
                    self.logger.error(
                        f"Failed to process specialized image {processed_file.relative_path}: {e}", exc_info=True
                    )
                    candidate.exclusion_reason = ExclusionReason.CONVERSION_FAILED
                candidates.append(candidate)
                continue

            if ext not in self._SUPPORTED_EXTENSIONS:
                inferred_ext = self.file_type_provider.infer_extension(processed_file.content)
                candidate.inferred_extension = inferred_ext

                if inferred_ext and self.converter_service.is_supported_for_conversion(inferred_ext):
                    try:
                        self.logger.info(
                            f"Attempting fallback conversion to PDF for {processed_file.relative_path} "
                            f"(inferred type: {inferred_ext})"
                        )
                        converted_content = self.converter_service.convert_to_pdf(processed_file.content, inferred_ext)
                        candidate.ai_content = converted_content
                        candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.pdf"
                        candidate.prepared_content_gcs_uris = [candidate.ai_path]
                        candidate.used_fallback_conversion = True
                    except Exception as e:
                        self.logger.warning(
                            f"Fallback conversion to PDF failed for {processed_file.relative_path}. "
                            f"Attempting secondary fallback to PNG with ImageMagick. Error: {e}",
                        )
                        try:
                            converted_content = self.image_converter_provider.to_png(
                                processed_file.content, inferred_ext
                            )
                            candidate.ai_content = converted_content
                            candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.png"
                            candidate.prepared_content_gcs_uris = [candidate.ai_path]
                            candidate.used_fallback_conversion = True
                        except Exception as e2:
                            self.logger.warning(
                                f"Secondary fallback conversion to PNG also failed for "
                                f"{processed_file.relative_path}. Error: {e2}",
                                exc_info=True,
                            )
                            candidate.exclusion_reason = ExclusionReason.CONVERSION_FAILED
                    candidates.append(candidate)
                    continue
                elif inferred_ext in self._SUPPORTED_EXTENSIONS:
                    ext = inferred_ext
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}{inferred_ext}"
                else:
                    candidate.exclusion_reason = ExclusionReason.UNSUPPORTED_EXTENSION
                    candidates.append(candidate)
                    continue

            try:
                if ext == ".docx":
                    converted_content = self.converter_service.docx_to_pdf(processed_file.content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.pdf"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".rtf":
                    converted_content = self.converter_service.rtf_to_pdf(processed_file.content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.pdf"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".doc":
                    converted_content = self.converter_service.doc_to_pdf(processed_file.content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.pdf"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".odt":
                    converted_content = self.converter_service.odt_to_pdf(processed_file.content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.pdf"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext in (".odg", ".pptx", ".xlsm", ".docm"):
                    converted_content = self.converter_service.convert_to_pdf(processed_file.content, ext)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.pdf"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".bmp":
                    converted_content = self.converter_service.bmp_to_png(processed_file.content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.png"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext == ".gif":
                    converted_content = self.converter_service.gif_to_mp4(processed_file.content)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.mp4"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif self.file_type_provider.get_file_type(ext) == SPECIALIZED_IMAGE:
                    converted_content = self.image_converter_provider.to_png(processed_file.content, ext)
                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.png"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext in (".xml", ".json", ".log", ".htm", ".html"):
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.txt"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                elif ext in self._SPREADSHEET_EXTENSIONS:
                    if ext == ".xls":
                        converted_content = self.converter_service.xls_to_pdf(processed_file.content)
                    elif ext == ".xlsx":
                        converted_content = self.converter_service.xlsx_to_pdf(processed_file.content)
                    elif ext == ".xlsb":
                        converted_content = self.converter_service.xlsb_to_pdf(processed_file.content)
                    else:
                        converted_content = self.converter_service.ods_to_pdf(processed_file.content)

                    candidate.ai_content = converted_content
                    candidate.ai_path = f"{os.path.splitext(processed_file.relative_path)[0]}.pdf"
                    candidate.prepared_content_gcs_uris = [candidate.ai_path]
                else:
                    if not candidate.prepared_content_gcs_uris:
                        candidate.prepared_content_gcs_uris = [candidate.ai_path]

            except Exception as e:
                self.logger.error(f"Failed to process file {processed_file.relative_path}: {e}", exc_info=True)
                candidate.exclusion_reason = ExclusionReason.CONVERSION_FAILED

            candidates.append(candidate)
        return candidates

    def _select_files_by_token_limit(
        self,
        candidates: list[AIFileCandidate],
        procurement: Procurement,
    ) -> list[AIFileCandidate]:
        """Selects which files to include based on the AI model's token limit.

        Args:
            candidates: A list of AIFileCandidate objects to select from.
            procurement: The procurement being analyzed.

        Returns:
            The list of candidates with updated inclusion status and warnings.
        """
        candidates.sort(key=self._get_priority)
        max_tokens = self.config.GCP_GEMINI_MAX_INPUT_TOKENS

        base_prompt_text = self._build_analysis_prompt(procurement, candidates)
        files_for_ai_uris: list[str] = []
        for candidate in candidates:
            if candidate.exclusion_reason:
                continue

            uris_to_test = files_for_ai_uris + candidate.ai_gcs_uris
            tokens, _, _ = self.ai_provider.count_tokens_for_analysis(base_prompt_text, uris_to_test)

            if tokens <= max_tokens:
                files_for_ai_uris.extend(candidate.ai_gcs_uris)
                candidate.is_included = True
            else:
                candidate.exclusion_reason = ExclusionReason.TOKEN_LIMIT_EXCEEDED
                candidate.applied_token_limit = max_tokens
                candidate.exclusion_reason_args = {"max_tokens": max_tokens}

        return candidates

    def _process_and_save_source_documents(
        self,
        analysis_id: UUID,
        candidates: list[AIFileCandidate],
    ) -> dict[str, UUID]:
        """Saves unique source documents to the database.

        Args:
            analysis_id: The ID of the current analysis.
            candidates: A list of all file candidates.

        Returns:
            A dictionary mapping synthetic source document IDs to their new database UUIDs.
        """
        source_docs_map: dict[str, UUID] = {}
        unique_source_docs = {c.synthetic_id: c.raw_document_metadata for c in candidates}

        for synthetic_id, raw_meta in unique_source_docs.items():
            doc_model = NewSourceDocument(
                analysis_id=analysis_id,
                synthetic_id=str(synthetic_id),
                title=raw_meta.get("titulo", "N/A"),
                publication_date=raw_meta.get("dataPublicacaoPncp"),
                document_type_name=raw_meta.get("tipoDocumentoNome"),
                url=raw_meta.get("url"),
                raw_metadata=raw_meta,
            )
            db_id = self.source_document_repo.save_source_document(doc_model)
            source_docs_map[synthetic_id] = db_id
        return source_docs_map

    def _update_selected_file_records(self, candidates: list[AIFileCandidate]) -> None:
        """Updates the database records for files that were selected for analysis.

        Args:
            candidates: The list of candidates after the selection process.
        """
        selected_file_ids = [
            candidate.file_record_id for candidate in candidates if candidate.is_included and candidate.file_record_id
        ]
        if selected_file_ids:
            self.file_record_repo.set_files_as_included(selected_file_ids)

    def _upload_and_save_initial_records(
        self,
        procurement: Procurement,
        procurement_id: UUID,
        analysis_id: UUID,
        candidates: list[AIFileCandidate],
        source_docs_map: dict[str, UUID],
    ) -> None:
        """Uploads all files to GCS and saves their initial metadata records.

        This method uploads both original and prepared files, populates the
        candidate objects with real GCS URIs, and saves the initial file
        record to the database with `included_in_analysis` set to False.

        Args:
            procurement: The procurement object.
            procurement_id: The database UUID of the procurement.
            analysis_id: The ID of the current analysis.
            candidates: A list of AIFileCandidate objects to upload and save.
            source_docs_map: A map of synthetic source IDs to database UUIDs.
        """
        bucket_name = self.config.GCP_GCS_BUCKET_PROCUREMENTS
        for candidate in candidates:
            source_document_db_id = source_docs_map[candidate.synthetic_id]
            ibge_code = procurement.entity_unit.ibge_code
            standard_path = f"{ibge_code}/{procurement_id}/{analysis_id}/{source_document_db_id}"
            base_gcs_path = f"{self.gcs_path_prefix}/{standard_path}" if self.gcs_path_prefix else standard_path
            original_gcs_path = f"{base_gcs_path}/{os.path.basename(candidate.original_path)}"

            self.gcs_provider.upload_file(
                bucket_name=bucket_name,
                destination_blob_name=original_gcs_path,
                content=candidate.original_content,
                content_type="application/octet-stream",
            )

            final_converted_uris = []
            if candidate.prepared_content_gcs_uris:
                prepared_gcs_path = f"{base_gcs_path}/prepared_content/{os.path.basename(candidate.ai_path)}"
                self.gcs_provider.upload_file(
                    bucket_name=bucket_name,
                    destination_blob_name=prepared_gcs_path,
                    content=candidate.ai_content,
                    content_type="application/octet-stream",
                )
                final_converted_uris = [f"gs://{bucket_name}/{prepared_gcs_path}"]

                candidate.ai_gcs_uris = final_converted_uris
                candidate.prepared_content_gcs_uris = final_converted_uris
            else:
                candidate.ai_gcs_uris = [f"gs://{bucket_name}/{original_gcs_path}"]

            prioritization_logic, prioritization_keyword = self._get_prioritization_logic(candidate)
            file_record = NewFileRecord(
                source_document_id=source_document_db_id,
                file_name=os.path.basename(candidate.original_path),
                gcs_path=original_gcs_path,
                extension=os.path.splitext(candidate.original_path)[1].lstrip("."),
                size_bytes=len(candidate.original_content),
                nesting_level=candidate.original_path.count(os.sep),
                included_in_analysis=False,
                exclusion_reason=candidate.exclusion_reason,
                prioritization_logic=prioritization_logic,
                prioritization_keyword=prioritization_keyword,
                applied_token_limit=candidate.applied_token_limit,
                prepared_content_gcs_uris=candidate.prepared_content_gcs_uris,
                inferred_extension=candidate.inferred_extension,
                used_fallback_conversion=candidate.used_fallback_conversion,
            )
            candidate.file_record_id = self.file_record_repo.save_file_record(file_record)

    def _get_priority(self, candidate: AIFileCandidate) -> int:
        """Determines the priority of a file based on its metadata and name.

        Args:
            candidate: The AIFileCandidate to prioritize.

        Returns:
            The priority of the file as an integer.
        """
        document_type_name = candidate.raw_document_metadata.get("tipoDocumentoNome", "").lower()
        for i, keyword in enumerate(self._FILE_PRIORITY_ORDER):
            if keyword in document_type_name:
                return i

        path_lower = candidate.original_path.lower()
        for i, keyword in enumerate(self._FILE_PRIORITY_ORDER):
            if keyword in path_lower:
                return i

        return len(self._FILE_PRIORITY_ORDER)

    def _get_prioritization_logic(self, candidate: AIFileCandidate) -> tuple[PrioritizationLogic, str | None]:
        """Returns the priority keyword found in the file's metadata or path.

        Args:
            candidate: The AIFileCandidate to get the priority string for.

        Returns:
            A tuple containing the prioritization logic and the keyword found.
        """
        document_type_name = candidate.raw_document_metadata.get("tipoDocumentoNome", "").lower()
        for keyword in self._FILE_PRIORITY_ORDER:
            if keyword in document_type_name:
                return PrioritizationLogic.BY_METADATA, keyword
        path_lower = candidate.original_path.lower()
        for keyword in self._FILE_PRIORITY_ORDER:
            if keyword in path_lower:
                return PrioritizationLogic.BY_KEYWORD, keyword
        return PrioritizationLogic.NO_PRIORITY, None

    def _build_analysis_prompt(
        self,
        procurement: Procurement,
        candidates: list[AIFileCandidate],
    ) -> str:
        """Constructs the prompt for the AI, including contextual warnings.

        Args:
            procurement: The procurement to build the prompt for.
            candidates: The list of file candidates for the analysis.

        Returns:
            The prompt for the AI.
        """
        procurement_summary = {
            "Objeto": procurement.object_description,
            "Modalidade": procurement.modality,
            "Órgão": procurement.government_entity.name,
            "Unidade": procurement.entity_unit.unit_name,
            "Valor Estimado": (
                f"R$ {procurement.total_estimated_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                if procurement.total_estimated_value is not None
                else "N/A"
            ),
            "Abertura das Propostas": (
                procurement.proposal_opening_date.strftime("%d/%m/%Y %H:%M")
                if procurement.proposal_opening_date
                else "N/A"
            ),
            "Encerramento das Propostas": (
                procurement.proposal_closing_date.strftime("%d/%m/%Y %H:%M")
                if procurement.proposal_closing_date
                else "N/A"
            ),
            "Data de Execução desta Análise (Hoje)": datetime.now().strftime("%d/%m/%Y"),
        }
        procurement_summary_str = json.dumps(procurement_summary, indent=2, ensure_ascii=False)

        source_doc_files = defaultdict(list)
        for candidate in candidates:
            source_doc_files[candidate.synthetic_id].append(candidate)

        document_context_parts = []
        for _source_id, files in source_doc_files.items():
            meta = files[0].raw_document_metadata
            title = meta.get("titulo", "N/A")
            doc_type = meta.get("tipoDocumentoNome", "N/A")
            doc_type_description = meta.get("tipoDocumentoDescricao", "N/A")
            pub_date = meta.get("dataPublicacaoPncp", "N/A")

            file_lines = []
            for file_candidate in files:
                notes = []
                if file_candidate.ai_path != file_candidate.original_path:
                    notes.append(f"originalmente `{file_candidate.original_path}`")

                if file_candidate.exclusion_reason:
                    warning_message = file_candidate.exclusion_reason.format_message(
                        **file_candidate.exclusion_reason_args
                    )
                    notes.append(f"AVISO: {warning_message}")

                note_str = ""
                if notes:
                    note_str = f" ({', '.join(notes)})"

                disposition = "INCLUÍDO" if file_candidate.is_included else "IGNORADO"
                file_lines.append(f"- `{os.path.basename(file_candidate.ai_path)}` [{disposition}]{note_str}")
            file_list = "\n".join(file_lines)

            context_part = (
                f"**Fonte do Documento:** {title} (Tipo: {doc_type} - "
                f"{doc_type_description}, Publicado em: {pub_date})\n"
                f"**Arquivos extraídos desta fonte:**\n{file_list}"
            )
            document_context_parts.append(context_part)

        if not candidates:
            document_context_section = (
                "ATENÇÃO: NENHUM DOCUMENTO FOI ENCONTRADO PARA ESTA LICITAÇÃO. "
                "A ANÁLISE DEVE SER FEITA APENAS COM BASE NO SUMÁRIO ACIMA."
            )
        else:
            document_context_section = "\n\n---\n\n".join(document_context_parts)

        return f"""
        Você é um Auditor de Controle Externo do Tribunal de Contas da União (TCU), especializado em análise forense de licitações públicas no Brasil, atuando sob a égide da Lei 14.133/2021 e da jurisprudência consolidada.

        --- PRINCÍPIOS ORIENTADORES (RIGOR E CETICISMO) ---
        1. **Ceticismo Profissional:** Assuma uma postura neutra e investigativa. O ônus da prova da irregularidade é seu.
        2. **Materialidade e Relevância:** Concentre-se em achados que tenham impacto financeiro significativo ou que violem princípios legais fundamentais.
        3. **Verificação de Fatos:** Toda informação externa utilizada (preços, notícias, dados de empresas) deve vir de fontes confiáveis e verificáveis. Priorize dados governamentais oficiais.
        4. **Restrição Negativa (Anti-Falso Positivo):** Se a evidência for ambígua, fraca ou a pesquisa de mercado for inconclusiva, NÃO reporte a irregularidade. Prefira errar por omissão do que acusar sem provas robustas.
        --- FIM DOS PRINCÍPIOS ---

        Revise os metadados e os documentos anexos para realizar a auditoria.

        --- SUMÁRIO DA LICITAÇÃO (Contexto) ---
        {procurement_summary_str}
        // NOTA: A data de referência da pesquisa de preços ou a data de abertura é crucial para a análise temporal.
        --- FIM DO SUMÁRIO ---

        --- CONTEXTO DOS DOCUMENTOS ANEXADOS ---
        {document_context_section}
        --- FIM DO CONTEXTO ---

        ### PROTOCOLO DE ANÁLISE OBRIGATÓRIO (Chain-of-Thought)

        1. **Análise da Fase Interna e Competitividade:** Examine a conformidade do Termo de Referência/Edital, buscando direcionamentos (marca sem justificativa técnica) ou restrições indevidas à competitividade.
        2. **Análise da Pesquisa de Preços do Órgão:** Avalie a metodologia utilizada pelo órgão. Eles seguiram a hierarquia legal? A pesquisa foi ampla? Há indícios de simulação ou cotações viciadas?
        3. **Auditoria de Economicidade (Verificação de Sobrepreço):** Etapa crítica. Utilize as ferramentas de busca (ex: Google Search) seguindo a metodologia abaixo. Inicie as buscas obrigatoriamente por termos como: "Painel de Preços [Objeto]", "Licitação Homologada [Objeto]", "Ata de Registro de Preços [Objeto]".

        ---
        #### METODOLOGIA DE ANÁLISE DE PREÇOS (OBRIGATÓRIA)

        Ao analisar Sobrepreço ou Superfaturamento, siga esta hierarquia e aplique as regras de validação:

        **I. HIERARQUIA DE FONTES (Siga a ordem estritamente):**
            A. **Fontes Públicas Oficiais:** Painel de Preços (Gov.br), Bancos de Preços Estaduais/Municipais (ex: BEC/SP), Contratações similares recentes no PNCP, Atas de Registro de Preço (ARP) vigentes.
            B. **Tabelas Indexadas:** SINAPI (obras), SIGTAP/BPS (saúde), ou outras tabelas setoriais oficiais.
            C. **Fontes B2B (Atacado/Distribuidores):** Sites de atacado ou distribuidores que vendem para empresas/governo.
            D. **Fontes B2C (Varejo/E-commerce) - USO EXCEPCIONAL:** Utilize APENAS se as fontes A-C forem exauridas.

        **II. REGRAS DE VALIDAÇÃO E CONTEXTUALIZAÇÃO:**

            1. **Temporalidade (CRÍTICO):** A pesquisa DEVE focar em preços contemporâneos à Data de Referência da licitação (janela de +/- 6 meses). Se utilizar preços fora desta janela, você DEVE mencionar a necessidade de ajuste inflacionário (ex: IPCA/INPC) no campo `rationale`.
            2. **Comparabilidade:** Garanta que a especificação técnica, marca, modelo e quantidade sejam idênticos ou funcionalmente equivalentes (justifique a equivalência).
            3. **Evidência Robusta (OBRIGATÓRIO):**
                *   **Fontes Privadas (C ou D):** É **PROIBIDO** concluir sobrepreço com base em apenas 1 ou 2 fontes. Você **DEVE** encontrar e citar no mínimo **3 fontes distintas** para formar uma Cesta de Preços de Mercado. Se não encontrar 3, não aponte sobrepreço (Restrição Negativa).
                *   **Fontes Oficiais (A ou B):** Se encontrar 1 fonte oficial robusta (ex: Painel de Preços ou Licitação similar no PNCP), ela é suficiente e tem preferência sobre fontes privadas.
            4. **Busca Exaustiva de Fontes Oficiais:** Antes de recorrer ao Google (Varejo), você **DEVE** tentar buscar em fontes oficiais. Se não encontrar, declare explicitamente no `auditor_reasoning`: "Foram realizadas buscas no Painel de Preços e no PNCP para a marca [MARCA], sem identificação de contratos comparáveis; por isso recorreu-se a fontes de varejo...".
            5. **Tratamento de Fontes de Varejo (B2C - Fonte D):** Se utilizar o varejo:
                *   **Fator de Desconto (BDI Diferencial):** Aplique um desconto presumido de 20% sobre o preço de varejo. No `rationale`, mostre a conta: "Preço varejo: R$ X/un. Aplicando fator de desconto de 20%: X * 0.80 = R$ Y/un (preço atacado estimado)."
                *   **Ressalvas (Custo Brasil):** Pondere o impacto de custos logísticos, tributários (ex: ICMS interestadual) e burocráticos específicos da contratação.
                *   **Agravante Crítico:** Se o preço contratado (em quantidade de atacado) for SUPERIOR ao preço de varejo unitário (sem desconto), isso é um indício GRAVE de sobrepreço, pois ignora a economia de escala.

        ---

        **III. REGRAS DE PREENCHIMENTO DA LISTA `sources` (CRÍTICO):**
            1. **Identificação da Fonte (ANTI-ALUCINAÇÃO):** Priorize o preenchimento do campo `name` com o nome da loja ou entidade (ex: "Kalunga", "Mercado Livre", "Painel de Preços"). As URLs de busca (Grounding) serão capturadas automaticamente pelo sistema e vinculadas à análise, portanto, concentre-se em identificar corretamente a origem do preço.
            2. **Quantidade de Fontes:**
                *   Cite **todas** as fontes relevantes encontradas que sustentem o achado. Não se limite a 3 fontes se houver mais evidências disponíveis.
                *   Se encontrar apenas **1 fonte válida** (e não for oficial), o `severity` DEVE ser rebaixado para **MODERADA** ou **LEVE**, pois a prova é frágil.
                *   Para sustentar `severity` **GRAVE** ou **CRÍTICO** em sobrepreço, é OBRIGATÓRIO citar **3 fontes** ou 1 fonte oficial.
            3. **Data da Referência:** Se a data não for explícita na página, use a data atual da consulta. **JAMAIS invente datas passadas.** Se a data for antiga (> 6 meses), justifique explicitamente no `rationale` por que ela ainda é válida.
            4. **Consistência (Checklist):**
                *   **Quantidade:** Verifique se a quantidade usada no cálculo de economia (ex: 1656) bate com a soma dos itens onde houve sobrepreço. Se excluir itens (ex: item 3), explique: "Considerando apenas os itens 1 e 2...".
                *   **Marca:** Padronize a grafia da marca (ex: Maxprint vs Maxxprint). Use a grafia do documento, mas mencione variações se necessário.
                *   **Preço de Referência:** Se usar uma média (ex: R$ 2,13), explique a origem: "Média entre Fonte A (R$ 2,00) e Fonte B (R$ 2,26)".

        **CATEGORIAS DE IRREGULARIDADES:**
        [DIRECIONAMENTO, RESTRICAO_COMPETITIVIDADE, SOBREPRECO (requer metodologia acima), SUPERFATURAMENTO (requer prova de dano consumado), FRAUDE (conluio, documentos falsos), DOCUMENTACAO_IRREGULAR, OUTROS]

        **ESTRUTURA DO `red_flag`:**
        - `category`: Categoria acima.
        - `severity`: `LEVE`, `MODERADA` ou `GRAVE`.
        - `description`: Descrição objetiva (pt-br).
        - `evidence_quote`: Citação literal (pt-br) do documento da licitação.
        - `auditor_reasoning`: Justificativa técnica (pt-br). Explique o risco e a norma violada.
            *   **OBRIGATÓRIO 1 (Fontes Oficiais):** Se não encontrou fontes oficiais, declare: "Foram realizadas buscas no Painel de Preços e no PNCP... sem sucesso". Se encontrou, cite-as.
            *   **OBRIGATÓRIO 2 (Justificativa de Severidade):** Se o sobrepreço for alto (>35%) mas a severidade for rebaixada para MODERADA por baixa materialidade, JUSTIFIQUE: "Apesar do percentual elevado (>35%), a severidade foi classificada como MODERADA em razão da baixa materialidade global...".
        - `potential_savings` (opcional): Valor monetário estimado da economia potencial. No `auditor_reasoning`, você DEVE explicitar a fórmula usada com os valores EXATOS: "Considerando preço referência R$ X (média/menor), a economia é: (Preço Contratado - Preço Ref) * Quantidade = R$ Y".
        - `sources` (Obrigatório para SOBREPRECO/SUPERFATURAMENTO):
            - `name`: nome ou título da fonte.
            - `type`: Classificação da fonte conforme hierarquia: "OFICIAL", "TABELA", "B2B" ou "VAREJO".
            - `reference_price`: preço de referência por unidade (quando disponível).
            - `price_unit`: unidade do valor (ex.: “unidade”, “metro”).
            - `reference_date`: data em que o preço foi válido ou coletado.
            - `evidence`: Trecho literal da fonte que apoia a comparação.
            - `rationale`: **(CRÍTICO)** Explicação detalhada da comparação. DEVE incluir: o tipo da fonte usada (ex: Oficial, Varejo), o preço unitário contratado, o preço de referência médio (da cesta), o cálculo da diferença percentual, a contextualização temporal e, se aplicável (Fonte Varejo), o Fator de Desconto aplicado (mostre a conta: X * 0.80 = Y) e as Ressalvas ponderadas.

        **CLASSIFICAÇÃO DE SEVERIDADE (Calibrada para Rigor e Materialidade):**
        - **Leve:** Falhas formais sem impacto material, ou sobrepreço < 15% acima da Cesta de Preços Aceitável.
        - **Moderada:** Restrição de competitividade, sobrepreço entre 15% e 35%, ou pesquisa de preços metodologicamente falha (ex: ignorar fontes oficiais sem justificativa).
        - **Grave:** Direcionamento claro, ausência de pesquisa de preços válida, sobrepreço > 35% comprovado por fontes robustas (A, B ou C), Preço de atacado superior ao de varejo (Agravante Crítico), ou qualquer indício de fraude/dano consumado.

        **CRITÉRIOS PARA A NOTA DE RISCO (0 a 100):**
        A nota deve refletir a probabilidade de irregularidade E o impacto material (financeiro).

        **Escala de Risco:**
        - **0-10 (Mínimo):** Processo regular ou falhas formais irrelevantes.
        - **11-30 (Baixo):** Falhas formais leves, sem dano ao erário ou prejuízo à competitividade.
        - **31-50 (Moderado):** Indícios de restrição à competitividade ou sobrepreço em itens de baixo impacto financeiro.
        - **51-70 (Alto):** Sobrepreço significativo (>25%) em itens relevantes, direcionamento evidente ou restrição grave sem justificativa.
        - **71-90 (Crítico):** Sobrepreço grosseiro (>50%), "Jogo de Planilha", ou direcionamento flagrante em licitação de grande vulto.
        - **91-100 (Máximo):** Prova documental de fraude (conluio, falsificação) ou superfaturamento consumado com alto dano.

        **Fator de Correção por Materialidade (OBRIGATÓRIO):**
        - Para licitações de **baixo valor total** (ex: Dispensa < R$ 50k) ou itens de valor irrisório: **REDUZA a nota de risco em 20 a 30 pontos**, a menos que haja prova inequívoca de fraude (conluio/falsificação).
        - **Exemplo:** Um sobrepreço de 100% em uma compra de R$ 1.000,00 (dano potencial de R$ 500,00) deve ter risco **BAIXO a MODERADO (Nota 20-40)**, jamais Alto ou Crítico, pois o custo do controle excede o benefício.

        **FORMATO DA RESPOSTA (JSON):**
        Sua resposta deve ser um objeto JSON único e válido. Preencha os campos `procurement_summary`, `analysis_summary`, `risk_score_rationale` (pt-br, máx 3 sentenças cada) e `seo_keywords` (5-10 palavras-chave estratégicas: Objeto, Órgão, Cidade/Estado, Tipo de Irregularidade).
        """  # noqa: E501

    def _calculate_hash(self, files: list[tuple[str, bytes | list[bytes]]]) -> str:
        """Calculates a SHA-256 hash from the content of a list of files.

        Args:
            files: A list of tuples containing the file path and content.

        Returns:
            The SHA-256 hash of the file content.
        """
        hasher = hashlib.sha256()
        for _, content in sorted(files, key=lambda x: x[0]):
            if isinstance(content, list):
                for item in content:
                    hasher.update(item)
            else:
                hasher.update(content)
        return hasher.hexdigest()

    def _calculate_procurement_hash(self, procurement: Procurement, files: list[ProcessedFile]) -> str:
        """Calculates a SHA-256 hash for a procurement based on key fields and file metadata.

        Args:
            procurement: The procurement to hash.
            files: The list of files to include in the hash.

        Returns:
            The SHA-256 hash of the procurement.
        """
        procurement_key_data = {
            "process_number": procurement.process_number,
            "object_description": procurement.object_description,
            "legal_support": procurement.legal_support.model_dump(by_alias=True),
            "is_srp": procurement.is_srp,
            "modality": procurement.modality,
            "pncp_control_number": procurement.pncp_control_number,
            "procurement_status": procurement.procurement_status,
            "total_estimated_value": procurement.total_estimated_value,
            "total_awarded_value": procurement.total_awarded_value,
            "proposal_opening_date": procurement.proposal_opening_date,
            "proposal_closing_date": procurement.proposal_closing_date,
            "government_entity": procurement.government_entity.model_dump(by_alias=True),
            "entity_unit": procurement.entity_unit.model_dump(by_alias=True),
            "dispute_method": procurement.dispute_method,
        }

        files_metadata = [
            {"relative_path": file.relative_path, "metadata": file.raw_document_metadata}
            for file in sorted(files, key=lambda x: x.relative_path)
        ]

        procurement_data_str = json.dumps(procurement_key_data, sort_keys=True, default=str)
        files_metadata_str = json.dumps(files_metadata, sort_keys=True)

        combined_data = procurement_data_str + files_metadata_str
        return hashlib.sha256(combined_data.encode("utf-8")).hexdigest()

    def run_specific_analysis(self, analysis_id: UUID) -> None:
        """Triggers an analysis for a specific ID by publishing a message.

        Args:
            analysis_id: The ID of the analysis to trigger.
        """
        try:
            self.logger.info(f"Running specific analysis for analysis_id: {analysis_id}")
            analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
            if not analysis:
                self.logger.error(f"Analysis with ID {analysis_id} not found.")
                return

            if analysis.status != ProcurementAnalysisStatus.PENDING_ANALYSIS.value:
                self.logger.warning(
                    f"Analysis {analysis_id} is not in PENDING_ANALYSIS state (current: {analysis.status}). Skipping."
                )
                return

            self._update_status_with_history(
                analysis_id, ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS, "Worker picked up the task."
            )

            if not self.pubsub_provider:
                raise ValueError("PubSubProvider is not configured for AnalysisService")

            message_data = {
                "procurement_control_number": analysis.procurement_control_number,
                "version_number": analysis.version_number,
                "analysis_id": str(analysis_id),
            }
            message_json = json.dumps(message_data)
            message_bytes = message_json.encode()
            self.pubsub_provider.publish(self.config.GCP_PUBSUB_TOPIC_PROCUREMENTS, message_bytes)
            self.logger.info(f"Published analysis request for analysis_id {analysis_id} to Pub/Sub.")
        except Exception as e:
            raise AnalysisError(f"An unexpected error occurred during specific analysis: {e}") from e

    def run_pre_analysis(
        self,
        start_date: date,
        end_date: date,
        batch_size: int,
        sleep_seconds: int,
        max_messages: int | None = None,
    ) -> Iterator[tuple[str, Any]]:
        """Runs the pre-analysis job for a given date range as a generator.

        This method iterates through each day in the date range, fetches the
        procurements for that day, and processes them incrementally. It yields
        events to allow the caller (e.g., a CLI) to display detailed, real-time
        progress.

        Args:
            start_date: The start date of the date range.
            end_date: The end date of the date range.
            batch_size: The number of procurements to process in each batch.
            sleep_seconds: The number of seconds to sleep between batches.
            max_messages: The maximum number of messages to publish.

        Yields:
            Tuples representing progress events:
            - ("day_started", (current_date, total_days))
            - ("procurements_fetched", procurements_for_the_day)
            - ("procurement_processed", (procurement, raw_data))
            - ("fetching_pages_started", (modality_name, total_pages))
            - ("page_fetched", page_number)
        """
        try:
            self.logger.info(f"Starting pre-analysis job for date range: {start_date} to {end_date}")
            total_days = (end_date - start_date).days + 1
            messages_published_count = 0
            processed_in_batch = 0
            for day_index in range(total_days):
                current_date = start_date + timedelta(days=day_index)
                yield "day_started", (current_date, total_days)
                procurements_for_the_day = []
                event_generator = self.procurement_repo.get_updated_procurements_with_raw_data(target_date=current_date)
                for event, data in event_generator:
                    if event == "modality_started":
                        modality_name = data
                    elif event == "pages_total":
                        yield "fetching_pages_started", (modality_name, data)
                    elif event == "procurements_page":
                        procurements_for_the_day.append(data)
                    elif event == "page_fetched":
                        yield "page_fetched", data
                yield "procurements_fetched", procurements_for_the_day
                if not procurements_for_the_day:
                    continue
                for procurement, raw_data in procurements_for_the_day:
                    if max_messages is not None and messages_published_count >= max_messages:
                        self.logger.info(f"Reached max_messages ({max_messages}). Stopping pre-analysis.")
                        return
                    try:
                        self._pre_analyze_procurement(procurement, raw_data)
                        messages_published_count += 1
                        processed_in_batch += 1
                        yield "procurement_processed", (procurement, raw_data)
                        is_last_item = (procurement, raw_data) == procurements_for_the_day[-1]
                        if processed_in_batch % batch_size == 0 and not is_last_item:
                            self.logger.info(
                                f"Batch of {batch_size} processed. " f"Sleeping for {sleep_seconds} seconds."
                            )
                            time.sleep(sleep_seconds)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to pre-analyze procurement {procurement.pncp_control_number}: {e}",
                            exc_info=True,
                        )
            self.logger.info("Pre-analysis job for the entire date range has been completed.")
        except Exception as e:
            raise AnalysisError(f"An unexpected error occurred during pre-analysis: {e}") from e

    def run_pre_analysis_by_control_number(
        self,
        pncp_control_number: str,
    ) -> Iterator[tuple[str, Any]]:
        """Runs the pre-analysis job for a single procurement by its control number.

        This generator fetches a specific procurement and its raw data, then
        processes it, yielding events compatible with the batch pre-analysis
        flow for consistent progress tracking.

        Args:
            pncp_control_number: The PNCP control number of the procurement.

        Yields:
            Tuples representing progress events, mirroring the batch flow.
        """
        try:
            self.logger.info(f"Starting pre-analysis for PNCP control number: {pncp_control_number}")
            yield "day_started", (date.today(), 1)

            procurement, raw_data = self.procurement_repo.get_procurement_by_control_number(pncp_control_number)
            if not procurement or not raw_data:
                self.logger.error(f"Procurement with PNCP control number {pncp_control_number} not found.")
                return

            yield "procurements_fetched", [(procurement, raw_data)]

            self._pre_analyze_procurement(procurement, raw_data)
            yield "procurement_processed", (procurement, raw_data)

            self.logger.info(f"Successfully pre-analyzed procurement {pncp_control_number}.")
        except Exception as e:
            raise AnalysisError(
                f"An unexpected error occurred during pre-analysis for {pncp_control_number}: {e}"
            ) from e

    def _pre_analyze_procurement(self, procurement: Procurement, raw_data: dict) -> None:
        """Performs the pre-analysis for a single procurement.

        This method handles the initial processing before the main AI analysis.
        It includes preparing file candidates, calculating content hashes, saving
        the initial procurement version and analysis records, selecting files
        based on token limits, and calculating the final estimated cost and
        priority score.

        Args:
            procurement: The procurement to pre-analyze.
            raw_data: The raw data of the procurement.
        """
        all_original_files = self.procurement_repo.process_procurement_documents(procurement)
        procurement_content_hash = self._calculate_procurement_hash(procurement, all_original_files)
        if self.procurement_repo.get_procurement_by_hash(procurement_content_hash):
            self.logger.info(f"Procurement with hash {procurement_content_hash} already exists. Skipping.")
            return

        all_candidates = self._prepare_ai_candidates(all_original_files)
        files_for_hash = [(c.ai_path, c.ai_content) for c in all_candidates if not c.exclusion_reason]
        analysis_document_hash = self._calculate_hash(files_for_hash)

        latest_version = self.procurement_repo.get_latest_version(procurement.pncp_control_number)
        new_version = latest_version + 1
        self.procurement_repo.save_procurement_version(
            procurement=procurement,
            raw_data=json.dumps(raw_data, sort_keys=True),
            version_number=new_version,
            content_hash=procurement_content_hash,
        )

        procurement_id = self.procurement_repo.get_procurement_uuid(procurement.pncp_control_number, new_version)
        if not procurement_id:
            raise AnalysisError(f"Could not find procurement UUID for {procurement.pncp_control_number} v{new_version}")

        analysis_id = self.analysis_repo.create_pre_analysis_record(
            procurement_control_number=procurement.pncp_control_number,
            version_number=new_version,
            document_hash=analysis_document_hash,
        )

        correlation_id = f"{procurement_id}:{analysis_id}:{uuid.uuid4().hex[:8]}"
        with LoggingProvider().set_correlation_id(correlation_id):
            source_docs_map = self._process_and_save_source_documents(analysis_id, all_candidates)
            self._upload_and_save_initial_records(
                procurement, procurement_id, analysis_id, all_candidates, source_docs_map
            )

            final_candidates = self._select_files_by_token_limit(all_candidates, procurement)
            prompt = self._build_analysis_prompt(procurement, final_candidates)
            uris_for_token_count = [uri for c in final_candidates if c.is_included for uri in c.ai_gcs_uris]
            input_tokens, _, _ = self.ai_provider.count_tokens_for_analysis(prompt, uris_for_token_count)

            output_tokens = self.config.GCP_GEMINI_MAX_OUTPUT_TOKENS
            thinking_tokens = 0
            modality = self._get_modality_from_exts([os.path.splitext(c.ai_path)[1] for c in final_candidates])
            (
                input_cost,
                output_cost,
                thinking_cost,
                search_cost,
                total_cost,
            ) = self.pricing_service.calculate_total_cost(
                input_tokens,
                output_tokens,
                thinking_tokens,
                modality=modality,
                search_queries_count=10,
            )

            self.analysis_repo.update_pre_analysis_with_tokens(
                analysis_id=analysis_id,
                input_tokens_used=input_tokens,
                output_tokens_used=output_tokens,
                thinking_tokens_used=thinking_tokens,
                input_cost=input_cost,
                output_cost=output_cost,
                thinking_cost=thinking_cost,
                search_cost=search_cost,
                total_cost=total_cost,
                search_queries_used=10,
                analysis_prompt=prompt,
            )

            db_procurement = self.procurement_repo.get_procurement_by_id_and_version(
                procurement.pncp_control_number, new_version
            )
            if db_procurement:
                db_procurement = self.ranking_service.calculate_priority(
                    db_procurement, all_candidates, analysis_id, input_tokens
                )
                self.procurement_repo.update_procurement_ranking_data(db_procurement, new_version)

            self._update_selected_file_records(final_candidates)
            self._update_status_with_history(
                analysis_id, ProcurementAnalysisStatus.PENDING_ANALYSIS, "Pre-analysis completed."
            )

    def run_ranked_analysis(
        self,
        use_auto_budget: bool,
        budget_period: str | None,
        zero_vote_budget_percent: int,
        budget: Decimal | None = None,
        max_messages: int | None = None,
    ) -> list[Any]:
        """Runs the ranked analysis job.

        Args:
            use_auto_budget: Whether to use the auto-budget calculation.
            budget_period: The period for the auto-budget calculation.
            zero_vote_budget_percent: The percentage of the budget to use for zero-vote analyses.
            budget: The manual budget to use.
            max_messages: The maximum number of messages to publish.

        Returns:
            A list of analyses that were triggered.
        """
        if use_auto_budget:
            if not budget_period:
                raise ValueError("Budget period must be provided for auto-budget calculation.")
            execution_budget = self._calculate_auto_budget(budget_period)
        elif budget is not None:
            execution_budget = budget
        else:
            raise ValueError("Either a manual budget must be provided or auto-budget must be enabled.")

        self.logger.info(f"Starting ranked analysis job with a budget of {execution_budget:.2f} BRL.")
        if max_messages is not None:
            self.logger.info(f"Analysis run is limited to a maximum of {max_messages} message(s).")

        remaining_budget = execution_budget
        zero_vote_budget = execution_budget * (Decimal(zero_vote_budget_percent) / 100)
        self.logger.info(f"Zero-vote budget is {zero_vote_budget:.2f} BRL.")

        pending_analyses = self.analysis_repo.get_pending_analyses_ranked()
        self.logger.info(f"Found {len(pending_analyses)} pending analyses.")
        triggered_analyses: list[Any] = []

        analyses_with_procurements = []
        for analysis in pending_analyses:
            procurement = self.procurement_repo.get_procurement_by_id_and_version(
                analysis.procurement_control_number, analysis.version_number
            )
            if not procurement:
                continue

            if not procurement.is_stable:
                self.logger.info(
                    f"Skipping analysis {analysis.analysis_id} for procurement "
                    f"{procurement.pncp_control_number} because it is not stable."
                )
                continue

            analyses_with_procurements.append((analysis, procurement))

        procurements_by_city = defaultdict(list)
        for analysis, procurement in analyses_with_procurements:
            procurements_by_city[procurement.entity_unit.ibge_code].append((analysis, procurement))

        total_eligible = len(analyses_with_procurements)
        city_allocations = {
            city_code: round(len(procurements) / total_eligible * (max_messages or total_eligible))
            for city_code, procurements in procurements_by_city.items()
        }

        processed_procurements = []
        for city_code, allocation in city_allocations.items():
            processed_procurements.extend(
                sorted(procurements_by_city[city_code], key=lambda x: x[1].priority_score, reverse=True)[:allocation]
            )

        processed_procurements.sort(key=lambda x: x[1].priority_score, reverse=True)

        for analysis, procurement in processed_procurements:
            if remaining_budget <= 0:
                self.logger.info("Budget exhausted. Stopping job.")
                break

            if max_messages is not None and len(triggered_analyses) >= max_messages:
                self.logger.info(f"Reached max_messages limit of {max_messages}. Stopping job.")
                break

            estimated_cost = analysis.total_cost or Decimal(0)

            if estimated_cost > remaining_budget:
                self.logger.info(
                    f"Skipping analysis {analysis.analysis_id}. "
                    f"Cost ({estimated_cost:.2f} BRL) exceeds remaining "
                    f"budget ({remaining_budget:.2f} BRL)."
                )
                continue

            if analysis.votes_count == 0 and estimated_cost > zero_vote_budget:
                self.logger.info(
                    f"Skipping zero-vote analysis {analysis.analysis_id}. "
                    f"Cost ({estimated_cost:.2f} BRL) exceeds remaining "
                    f"zero-vote budget ({zero_vote_budget:.2f} BRL)."
                )
                continue

            self.logger.info(
                f"Processing analysis {analysis.analysis_id} with "
                f"priority score {procurement.priority_score} and "
                f"estimated cost of {estimated_cost:.2f} BRL."
            )
            try:
                self.run_specific_analysis(analysis.analysis_id)
                remaining_budget -= estimated_cost
                if analysis.votes_count == 0:
                    zero_vote_budget -= estimated_cost

                self.logger.info(
                    f"Analysis {analysis.analysis_id} triggered. "
                    f"Remaining budget: {remaining_budget:.2f} BRL. "
                    f"Zero-vote budget: {zero_vote_budget:.2f} BRL."
                )
                triggered_analyses.append(analysis)
            except Exception as e:
                self.logger.error(
                    f"Failed to trigger analysis {analysis.analysis_id}: {e}",
                    exc_info=True,
                )

        self.logger.info("Ranked analysis job completed.")
        return triggered_analyses

    def retry_analyses(self, initial_backoff_hours: int, max_retries: int, timeout_hours: int) -> int:
        """Retries failed or stale analyses.

        Args:
            initial_backoff_hours: The initial backoff in hours.
            max_retries: The maximum number of retries.
            timeout_hours: The timeout in hours.

        Returns:
            The number of analyses retried.
        """
        try:
            analyses_to_retry = self.analysis_repo.get_analyses_to_retry(max_retries, timeout_hours)
            retried_count = 0

            for analysis in analyses_to_retry:
                now = datetime.now(timezone.utc)
                last_updated = analysis.updated_at.replace(tzinfo=timezone.utc)
                backoff_hours = initial_backoff_hours * (2**analysis.retry_count)
                next_retry_time = last_updated + timedelta(hours=backoff_hours)

                if now < next_retry_time:
                    continue

                if analysis.status == ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value:
                    self.logger.info(f"Resuming pre-analysis for stuck analysis {analysis.analysis_id}...")
                    try:
                        self._resume_pre_analysis(analysis)
                        self.run_specific_analysis(analysis.analysis_id)
                        retried_count += 1
                    except Exception as e:
                        self.logger.error(
                            f"Failed to resume pre-analysis for {analysis.analysis_id}: {e}", exc_info=True
                        )
                        self._update_status_with_history(
                            analysis.analysis_id,
                            ProcurementAnalysisStatus.ANALYSIS_FAILED,
                            f"Pre-analysis resumption failed: {e}",
                        )
                else:
                    self.logger.info(f"Retrying analysis {analysis.analysis_id}...")
                    modality = Modality.TEXT
                    (
                        input_cost,
                        output_cost,
                        thinking_cost,
                        search_cost,
                        total_cost,
                    ) = self.pricing_service.calculate_total_cost(
                        analysis.input_tokens_used,
                        analysis.output_tokens_used,
                        analysis.thinking_tokens_used,
                        modality=modality,
                        search_queries_count=analysis.search_queries_used or 0,
                    )
                    new_analysis_id = self.analysis_repo.save_retry_analysis(
                        procurement_control_number=analysis.procurement_control_number,
                        version_number=analysis.version_number,
                        document_hash=analysis.document_hash,
                        input_tokens_used=analysis.input_tokens_used,
                        output_tokens_used=analysis.output_tokens_used,
                        thinking_tokens_used=analysis.thinking_tokens_used,
                        input_cost=input_cost,
                        output_cost=output_cost,
                        thinking_cost=thinking_cost,
                        search_cost=search_cost,
                        total_cost=total_cost,
                        search_queries_used=analysis.search_queries_used or 0,
                        retry_count=analysis.retry_count + 1,
                        analysis_prompt=analysis.analysis_prompt,
                    )
                    self.run_specific_analysis(new_analysis_id)
                    retried_count += 1

            return retried_count
        except Exception as e:
            raise AnalysisError(f"An unexpected error occurred during retry analyses: {e}") from e

    def _rebuild_candidates_from_db(self, analysis_id: UUID) -> list[AIFileCandidate]:
        """Rebuilds a list of AIFileCandidate objects from database records.

        Args:
            analysis_id: The ID of the analysis to rebuild candidates for.

        Returns:
            A list of AIFileCandidate objects.
        """
        file_records = self.file_record_repo.get_all_file_records_by_analysis_id(str(analysis_id))
        source_doc_ids = {record["source_document_id"] for record in file_records}
        source_docs = self.source_document_repo.get_source_documents_by_ids(list(source_doc_ids))
        source_docs_map = {doc.id: doc for doc in source_docs}

        candidates = []
        for record in file_records:
            source_doc = source_docs_map.get(record["source_document_id"])
            if not source_doc:
                self.logger.warning(f"Source document not found for file record: {record['file_record_id']}")
                continue

            relative_path = record["file_name"]

            prepared_uris = record.get("prepared_content_gcs_uris") or []
            if prepared_uris:
                ai_path = prepared_uris[0].split("/")[-1]
                ai_gcs_uris = prepared_uris
            else:
                ai_path = relative_path
                ai_gcs_uris = [f"gs://{self.config.GCP_GCS_BUCKET_PROCUREMENTS}/{record['gcs_path']}"]

            candidate = AIFileCandidate(
                synthetic_id=source_doc.synthetic_id,
                raw_document_metadata=source_doc.raw_metadata,
                original_path=relative_path,
                file_record_id=record["file_record_id"],
                ai_gcs_uris=ai_gcs_uris,
                ai_path=ai_path,
                exclusion_reason=record.get("exclusion_reason"),
            )
            candidates.append(candidate)
        return candidates

    def _resume_pre_analysis(self, analysis: AnalysisResult) -> None:
        """Resumes a pre-analysis that was stuck in PENDING_TOKEN_CALCULATION.

        Args:
            analysis: The analysis to resume.
        """
        self.logger.info(f"Resuming pre-analysis for {analysis.analysis_id}")
        analysis_id = analysis.analysis_id

        procurement = self.procurement_repo.get_procurement_by_id_and_version(
            analysis.procurement_control_number, analysis.version_number
        )
        if not procurement:
            raise AnalysisError(f"Procurement not found for resuming analysis {analysis_id}")

        all_candidates = self._rebuild_candidates_from_db(analysis_id)

        final_candidates = self._select_files_by_token_limit(all_candidates, procurement)
        prompt = self._build_analysis_prompt(procurement, final_candidates)
        uris_for_token_count = [uri for c in final_candidates if c.is_included for uri in c.ai_gcs_uris]
        input_tokens, _, _ = self.ai_provider.count_tokens_for_analysis(prompt, uris_for_token_count)

        output_tokens = self.config.GCP_GEMINI_MAX_OUTPUT_TOKENS
        thinking_tokens = 0
        modality = self._get_modality_from_exts([os.path.splitext(c.ai_path)[1] for c in final_candidates])
        (
            input_cost,
            output_cost,
            thinking_cost,
            search_cost,
            total_cost,
        ) = self.pricing_service.calculate_total_cost(
            input_tokens,
            output_tokens,
            thinking_tokens,
            modality=modality,
            search_queries_count=10,
        )

        self.analysis_repo.update_pre_analysis_with_tokens(
            analysis_id=analysis_id,
            input_tokens_used=input_tokens,
            output_tokens_used=output_tokens,
            thinking_tokens_used=thinking_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            thinking_cost=thinking_cost,
            search_cost=search_cost,
            total_cost=total_cost,
            search_queries_used=10,
            analysis_prompt=prompt,
        )

        db_procurement = self.procurement_repo.get_procurement_by_id_and_version(
            procurement.pncp_control_number, procurement.version_number
        )
        if db_procurement:
            db_procurement = self.ranking_service.calculate_priority(
                db_procurement, all_candidates, analysis_id, input_tokens
            )
            self.procurement_repo.update_procurement_ranking_data(db_procurement, procurement.version_number)

        self._update_selected_file_records(final_candidates)
        self._update_status_with_history(
            analysis_id, ProcurementAnalysisStatus.PENDING_ANALYSIS, "Pre-analysis resumed and completed."
        )
        self.logger.info(f"Successfully resumed pre-analysis for {analysis.analysis_id}")

    def get_procurement_overall_status(self, procurement_control_number: str) -> dict[str, Any] | None:
        """Retrieves the overall status of a procurement.

        Args:
            procurement_control_number: The control number of the procurement.

        Returns:
            The overall status of the procurement.
        """
        self.logger.info(f"Fetching overall status for procurement {procurement_control_number}.")
        status_info: dict[str, Any] | None = self.analysis_repo.get_procurement_overall_status(
            procurement_control_number
        )
        if not status_info:
            self.logger.warning(f"No overall status found for procurement {procurement_control_number}.")
            return None
        return status_info

    def _calculate_auto_budget(self, budget_period: str) -> Decimal:
        """Calculates the budget for the current run based on donation history and spending pace.

        Args:
            budget_period: The period for the auto-budget calculation.

        Returns:
            The calculated budget for the current run.
        """
        today = datetime.now(timezone.utc).date()
        if budget_period == "daily":
            start_of_period = today
            days_in_period = 1
            day_of_period = 1
        elif budget_period == "weekly":
            start_of_period = today - timedelta(days=today.weekday())
            days_in_period = 7
            day_of_period = today.weekday() + 1
        elif budget_period == "monthly":
            start_of_period = today.replace(day=1)
            next_month = start_of_period.replace(day=28) + timedelta(days=4)
            days_in_period = (next_month - timedelta(days=next_month.day)).day
            day_of_period = today.day
        else:
            raise ValueError(f"Invalid budget period: {budget_period}")

        current_balance = self.budget_ledger_repo.get_total_donations()
        expenses_in_period = self.budget_ledger_repo.get_total_expenses_for_period(start_of_period)
        period_capital = current_balance + expenses_in_period
        daily_target = period_capital / days_in_period
        cumulative_target_today = daily_target * day_of_period
        budget_for_this_run = cumulative_target_today - expenses_in_period

        self.logger.debug(
            f"Auto-budget calculation: Balance={current_balance:.2f}, "
            f"Expenses={expenses_in_period:.2f}, Capital={period_capital:.2f}, "
            f"DailyTarget={daily_target:.2f}, CumulativeTarget={cumulative_target_today:.2f}"
        )

        return Decimal(max(Decimal("0"), budget_for_this_run))
