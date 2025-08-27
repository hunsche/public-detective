import io
import os
import re
import tarfile
import tempfile
import zipfile
from datetime import date
from http import HTTPStatus
from urllib.parse import urljoin

import py7zr
import rarfile
import requests
from google.api_core import exceptions
from models.procurement import (
    DocumentType,
    Procurement,
    ProcurementDocument,
    ProcurementListResponse,
    ProcurementModality,
)
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider
from providers.pubsub import PubSubProvider
from pydantic import ValidationError
from sqlalchemy import Engine, text


class ProcurementRepository:
    """Repository for fetching procurement data and related documents from the
    PNCP API, extracting file metadata, and creating aggregated ZIP archives.

    It is designed to handle multiple compression formats, including ZIP, RAR,
    7z, and TAR archives, both at the root level and nested.
    """

    logger: Logger
    config: Config

    def __init__(self, engine: Engine, pubsub_provider: PubSubProvider) -> None:
        """Initializes the repository with its dependencies."""
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.pubsub_provider = pubsub_provider
        self.engine = engine

    def save_procurement(self, procurement: Procurement) -> None:
        """Saves a procurement object to the database."""
        self.logger.info(f"Saving procurement {procurement.pncp_control_number} to the database.")
        sql = text(
            """
            INSERT INTO procurement (
                pncp_control_number, proposal_opening_date, proposal_closing_date,
                object_description, total_awarded_value, is_srp, procurement_year,
                procurement_sequence, pncp_publication_date, last_update_date,
                modality_id, procurement_status_id, total_estimated_value
            ) VALUES (
                :pncp_control_number, :proposal_opening_date, :proposal_closing_date,
                :object_description, :total_awarded_value, :is_srp, :procurement_year,
                :procurement_sequence, :pncp_publication_date, :last_update_date,
                :modality_id, :procurement_status_id, :total_estimated_value
            )
            ON CONFLICT (pncp_control_number) DO NOTHING;
        """
        )
        params = {
            "pncp_control_number": procurement.pncp_control_number,
            "proposal_opening_date": procurement.proposal_opening_date,
            "proposal_closing_date": procurement.proposal_closing_date,
            "object_description": procurement.object_description,
            "total_awarded_value": procurement.total_awarded_value,
            "is_srp": procurement.is_srp,
            "procurement_year": procurement.procurement_year,
            "procurement_sequence": procurement.procurement_sequence,
            "pncp_publication_date": procurement.pncp_publication_date,
            "last_update_date": procurement.last_update_date,
            "modality_id": procurement.modality,
            "procurement_status_id": procurement.procurement_status,
            "total_estimated_value": procurement.total_estimated_value,
        }
        with self.engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()
        self.logger.info("Procurement saved successfully.")

    def process_procurement_documents(self, procurement: Procurement) -> list[tuple[str, bytes]]:
        """Downloads all documents for a procurement, extracts metadata for every
        file, and collects all final (non-archive) files.

        This is the main entry point method that orchestrates all file
        processing for a single procurement.

        Args:
            procurement: The procurement object to process.

        Returns:
            A list of tuples for all final files (file_path, content).
        """
        documents_to_download = self._get_all_documents_metadata(procurement)
        if not documents_to_download:
            return []

        final_files: list[tuple[str, bytes]] = []

        for doc in documents_to_download:
            content = self._download_file_content(doc.url)
            if not content:
                continue

            original_filename = self._determine_original_filename(doc.url) or doc.title

            self._recursive_file_processing(
                content=content,
                current_path=original_filename,
                nesting_level=0,
                file_collection=final_files,
            )

        return final_files

    def _recursive_file_processing(
        self,
        content: bytes,
        current_path: str,
        nesting_level: int,
        file_collection: list[tuple[str, bytes]],
    ) -> None:
        """Recursively processes byte content, dispatching to the correct
        archive handler based on the file extension or content.

        If the file is not a recognized archive type, it is treated as a
        final file to be collected.
        """
        lower_path = current_path.lower()
        handler = None

        if lower_path.endswith(".zip"):
            handler = self._extract_from_zip
        elif lower_path.endswith(".rar"):
            handler = self._extract_from_rar
        elif lower_path.endswith(".7z"):
            handler = self._extract_from_7z
        # tarfile.is_tarfile can identify .tar, .tar.gz, .tgz, .tar.bz2
        elif tarfile.is_tarfile(io.BytesIO(content)):
            handler = self._extract_from_tar

        if handler:
            try:
                nested_files = handler(content)
                for member_name, member_content in nested_files:
                    new_path = os.path.join(current_path, member_name)
                    self._recursive_file_processing(
                        member_content,
                        new_path,
                        nesting_level + 1,
                        file_collection,
                    )
            except Exception as e:
                self.logger.warning(f"Could not process archive '{current_path}': {e}. Treating " "as a single file.")
                file_collection.append((current_path, content))
        else:
            file_collection.append((current_path, content))

    def create_zip_from_files(self, files: list[tuple[str, bytes]], control_number: str) -> bytes | None:
        """Creates a single, flat ZIP archive in memory from a list of files."""
        if not files:
            return None
        self.logger.info(f"Creating final ZIP archive with {len(files)} files for " f"{control_number}...")
        zip_stream = io.BytesIO()
        try:
            with zipfile.ZipFile(zip_stream, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path, content in files:
                    safe_path = re.sub(r'[<>:"/\\|?*]', "_", file_path)
                    zf.writestr(safe_path, content)
            zip_bytes = zip_stream.getvalue()
            self.logger.info(f"Successfully created final ZIP archive of {len(zip_bytes)} bytes.")
            return zip_bytes
        except Exception as e:
            self.logger.error(f"Failed to create final ZIP archive for {control_number}: {e}")
            return None

    def _extract_from_zip(self, content: bytes) -> list[tuple[str, bytes]]:
        """Extracts all members from a ZIP archive."""
        extracted = []
        with io.BytesIO(content) as stream:
            with zipfile.ZipFile(stream) as archive:
                for member_info in archive.infolist():
                    if not member_info.is_dir():
                        extracted.append((member_info.filename, archive.read(member_info.filename)))
        return extracted

    def _extract_from_rar(self, content: bytes) -> list[tuple[str, bytes]]:
        """Extracts all members from a RAR archive."""
        extracted = []
        with io.BytesIO(content) as stream:
            with rarfile.RarFile(stream) as archive:
                for member_info in archive.infolist():
                    if not member_info.isdir():
                        extracted.append((member_info.filename, archive.read(member_info.filename)))
        return extracted

    def _extract_from_7z(self, content: bytes) -> list[tuple[str, bytes]]:
        """Extracts all members from a 7z archive."""
        extracted = []
        with tempfile.TemporaryDirectory() as tmpdir:
            with io.BytesIO(content) as stream:
                with py7zr.SevenZipFile(stream, mode="r") as archive:
                    archive.extractall(path=tmpdir)

            for root, _, files in os.walk(tmpdir):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    with open(filepath, "rb") as f:
                        file_content = f.read()
                    relative_path = os.path.relpath(filepath, tmpdir)
                    extracted.append((relative_path, file_content))
        return extracted

    def _extract_from_tar(self, content: bytes) -> list[tuple[str, bytes]]:
        """Extracts all members from a TAR archive (including .gz, .bz2)."""
        extracted = []
        with io.BytesIO(content) as stream:
            with tarfile.open(fileobj=stream, mode="r:*") as archive:
                for member_info in archive.getmembers():
                    if member_info.isfile():
                        file_obj = archive.extractfile(member_info)
                        if file_obj:
                            file_content = file_obj.read()
                            extracted.append((member_info.name, file_content))
        return extracted

    def _get_all_documents_metadata(self, procurement: Procurement) -> list[ProcurementDocument]:
        """Fetches and validates metadata for all active documents, prioritizing
        the 'BID_NOTICE'."""
        try:
            endpoint = (
                f"orgaos/{procurement.government_entity.cnpj}/compras/"
                f"{procurement.procurement_year}/{procurement.procurement_sequence}/arquivos"
            )
            api_url = urljoin(self.config.PNCP_INTEGRATION_API_URL, endpoint)
            response = requests.get(api_url, timeout=30)
            if response.status_code == HTTPStatus.NO_CONTENT:
                return []
            response.raise_for_status()

            all_docs = [ProcurementDocument.model_validate(doc) for doc in response.json()]
            active_docs = [doc for doc in all_docs if doc.is_active]

            if len(active_docs) < len(all_docs):
                self.logger.info(f"Filtered out {len(all_docs) - len(active_docs)} inactive documents.")

            active_docs.sort(key=lambda doc: doc.document_type_id != DocumentType.BID_NOTICE)
            self.logger.info(f"Found metadata for {len(active_docs)} active document(s).")
            return active_docs
        except (requests.RequestException, ValidationError) as e:
            self.logger.error(f"Failed to get/validate document list for {procurement.pncp_control_number}: {e}")
            return []

    def _download_file_content(self, url: str) -> bytes | None:
        """Downloads only the binary content of a file from a given URL."""
        try:
            self.logger.debug(f"Downloading content from {url}")
            response = requests.get(url, timeout=90)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            self.logger.error(f"Failed to download content from {url}: {e}")
            return None

    def _determine_original_filename(self, url: str) -> str | None:
        """Determines the original filename by making a HEAD request and checking
        the Content-Disposition header.
        """
        try:
            response = requests.head(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            content_disposition = response.headers.get("Content-Disposition")
            if content_disposition:
                match = re.search(r'filename="?([^"]+)"?', content_disposition, re.IGNORECASE)
                if match:
                    return match.group(1)
        except requests.RequestException as e:
            self.logger.warning(f"Could not determine filename from headers for {url}: {e}")
        return None

    def get_updated_procurements(self, target_date: date) -> list[Procurement]:
        """Fetches all procurements updated on a specific date by iterating through
        relevant modalities and configured city codes.
        """
        all_procurements: list[Procurement] = []
        modalities_to_check = [
            ProcurementModality.ELECTRONIC_REVERSE_AUCTION,
            ProcurementModality.BIDDING_WAIVER,
            ProcurementModality.BIDDING_UNENFORCEABILITY,
            ProcurementModality.ELECTRONIC_COMPETITION,
        ]
        self.logger.info(f"Fetching all procurements updated on {target_date}...")
        codes_to_check = self.config.TARGET_IBGE_CODES
        if not codes_to_check:
            self.logger.warning("No TARGET_IBGE_CODES configured. The search will be nationwide.")
            codes_to_check = [None]  # Perform one loop for nationwide search
        for city_code in codes_to_check:
            if city_code:
                self.logger.info(f"Searching for city with IBGE code: {city_code}")
            for modality in modalities_to_check:
                page = 1
                while True:
                    endpoint = "contratacoes/atualizacao"
                    params = {
                        "dataInicial": target_date.strftime("%Y%m%d"),
                        "dataFinal": target_date.strftime("%Y%m%d"),
                        "codigoModalidadeContratacao": str(modality.value),
                        "pagina": str(page),
                    }
                    if city_code:
                        params["codigoMunicipioIbge"] = city_code
                    try:
                        response = requests.get(
                            urljoin(self.config.PNCP_PUBLIC_QUERY_API_URL, endpoint),
                            params=params,
                            timeout=30,
                        )
                        if response.status_code == HTTPStatus.NO_CONTENT:
                            break
                        response.raise_for_status()
                        parsed_data = ProcurementListResponse.model_validate(response.json())
                        if not parsed_data.data:
                            break
                        all_procurements.extend(parsed_data.data)
                        if page >= parsed_data.total_pages:
                            break
                        page += 1
                    except requests.exceptions.RequestException as e:
                        self.logger.error(f"Error fetching updates on page {page}: {e}")
                        break
                    except ValidationError as e:
                        self.logger.error(f"Data validation error on page {page}: {e}")
                        break
        self.logger.info(f"Finished fetching. Total procurements: {len(all_procurements)}")
        return all_procurements

    def publish_procurement_to_pubsub(self, procurement: Procurement) -> bool:
        """Publishes a procurement object to the configured Pub/Sub topic."""
        try:
            message_json = procurement.model_dump_json(by_alias=True)
            message_bytes = message_json.encode()
            message_id = self.pubsub_provider.publish(self.config.GCP_PUBSUB_TOPIC_PROCUREMENTS, message_bytes)
            self.logger.debug(f"Successfully published message {message_id} for " f"{procurement.pncp_control_number}.")
            return True
        except exceptions.GoogleAPICallError as e:
            self.logger.error(f"Failed to publish message for {procurement.pncp_control_number}: {e}")
            return False
