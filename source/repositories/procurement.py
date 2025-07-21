import io
import re
import zipfile
from datetime import date
from http import HTTPStatus
from urllib.parse import urljoin

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


class ProcurementRepository:
    """Repository for fetching procurement data and related documents from the
    PNCP API and for publishing procurement messages to a queue.

    It aggregates all procurement documents into a single, well-structured
    ZIP archive for comprehensive analysis.
    """

    logger: Logger
    config: Config

    def __init__(self) -> None:
        """Initializes the repository with a logger and configuration."""
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()

    def get_document_content_as_zip(self, procurement: Procurement) -> bytes | None:
        """Finds all associated documents for a procurement, downloads them,
        and aggregates them into a single ZIP archive in memory, with each
        document or its extracted contents placed in a dedicated folder.

        Args:
            procurement: The procurement object containing metadata.

        Returns:
            The raw byte content of the newly created ZIP archive, or None
            if no documents could be processed.
        """
        documents_to_process = self._get_all_documents_metadata(procurement)
        if not documents_to_process:
            self.logger.warning(
                f"No active documents found for {procurement.pncp_control_number}."
            )
            return None

        return self._create_structured_zip(
            documents_to_process, procurement.pncp_control_number
        )

    def _get_all_documents_metadata(
        self, procurement: Procurement
    ) -> list[ProcurementDocument]:
        """Fetches and validates the metadata for all active documents associated
        with a procurement, prioritizing the 'BID_NOTICE' (Edital).

        Args:
            procurement: The procurement object.

        Returns:
            A sorted list of active ProcurementDocument models.
        """
        try:
            endpoint = (
                f"orgaos/{procurement.government_entity.cnpj}/compras/"
                f"{procurement.procurement_year}/{procurement.procurement_sequence}/arquivos"
            )
            api_url = urljoin(self.config.PNCP_INTEGRATION_API_URL, endpoint)
            self.logger.info(f"Fetching document list from: {api_url}")
            response = requests.get(api_url, timeout=30)

            if response.status_code == HTTPStatus.NO_CONTENT:
                self.logger.info(
                    f"No documents found (204) for {procurement.pncp_control_number}."
                )
                return []
            response.raise_for_status()

            all_documents = [
                ProcurementDocument.model_validate(doc) for doc in response.json()
            ]
            active_documents = [doc for doc in all_documents if doc.is_active]

            if len(active_documents) < len(all_documents):
                self.logger.info(
                    f"Filtered out {len(all_documents) - len(active_documents)} inactive documents."
                )

            active_documents.sort(
                key=lambda doc: doc.document_type_id != DocumentType.BID_NOTICE
            )

            self.logger.info(
                f"Found {len(active_documents)} active document(s) for processing."
            )
            return active_documents
        except (requests.RequestException, ValidationError) as e:
            self.logger.error(
                f"Failed to get or validate document list for {procurement.pncp_control_number}: {e}"
            )
            return []

    def _create_structured_zip(
        self, documents: list[ProcurementDocument], control_number: str
    ) -> bytes | None:
        """Creates a ZIP archive in memory, placing each document's contents
        inside a dedicated folder.

        If a downloaded document is a ZIP file, its contents are extracted into
        the folder. Otherwise, the document itself is placed in the folder.

        Args:
            documents: A list of document metadata objects to process.
            control_number: The procurement control number for logging.

        Returns:
            The byte content of the master ZIP file.
        """
        self.logger.info(f"Creating structured ZIP for {control_number}...")
        zip_stream = io.BytesIO()
        try:
            with zipfile.ZipFile(zip_stream, "w", zipfile.ZIP_DEFLATED) as master_zip:
                for doc in documents:
                    content = self._download_file_content(doc.url)
                    if not content:
                        continue

                    folder_name = f"{doc.document_sequence}_{doc.document_type_name.lower().replace(' ', '_')}"

                    if content.startswith(b"PK\x03\x04"):
                        self.logger.info(f"Extracting content into folder: {folder_name}")
                        with io.BytesIO(content) as inner_zip_stream:
                            with zipfile.ZipFile(inner_zip_stream) as inner_zip:
                                for member_name in inner_zip.namelist():
                                    if member_name.startswith(
                                        "__MACOSX"
                                    ) or member_name.endswith("/"):
                                        continue
                                    member_content = inner_zip.read(member_name)
                                    master_zip.writestr(
                                        f"{folder_name}/{member_name}", member_content
                                    )
                    else:
                        self.logger.info(f"Adding file to folder: {folder_name}")
                        original_filename = (
                            self._determine_original_filename(doc.url) or doc.title
                        )
                        master_zip.writestr(f"{folder_name}/{original_filename}", content)

            zip_bytes = zip_stream.getvalue()
            self.logger.info(
                f"Successfully created structured ZIP of {len(zip_bytes)} bytes."
            )
            return zip_bytes
        except Exception as e:
            self.logger.error(
                f"Failed to create structured ZIP for {control_number}: {e}"
            )
            return None

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
        """Determines the original filename by making a HEAD request and
        checking the Content-Disposition header.
        """
        try:
            response = requests.head(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            content_disposition = response.headers.get("Content-Disposition")
            if content_disposition:
                match = re.search(
                    r'filename="?([^"]+)"?', content_disposition, re.IGNORECASE
                )
                if match:
                    return match.group(1)
        except requests.RequestException as e:
            self.logger.warning(
                f"Could not determine filename from headers for {url}: {e}"
            )
        return None

    def get_updated_procurements(self, target_date: date) -> list[Procurement]:
        """Fetches all procurements updated on a specific date by iterating
        through relevant modalities and configured city codes.
        """
        all_procurements: list[Procurement] = []
        modalities_to_check = [
            ProcurementModality.ELECTRONIC_REVERSE_AUCTION,
            ProcurementModality.BIDDING_WAIVER,
            ProcurementModality.BIDDING_UNENFORCEABILITY,
            ProcurementModality.ELECTRONIC_COMPETITION,
        ]
        self.logger.info(f"Fetching all procurements updated on {target_date}...")
        if not self.config.TARGET_IBGE_CODES:
            self.logger.warning(
                "No TARGET_IBGE_CODES configured. The search will be nationwide."
            )
        for city_code in self.config.TARGET_IBGE_CODES:
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
                        parsed_data = ProcurementListResponse.model_validate(
                            response.json()
                        )
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
        self.logger.info(
            f"Finished fetching. Total procurements: {len(all_procurements)}"
        )
        return all_procurements

    def publish_procurement_to_pubsub(self, procurement: Procurement) -> bool:
        """Publishes a procurement object to the configured Pub/Sub topic."""
        try:
            message_json = procurement.model_dump_json(by_alias=True)
            message_bytes = message_json.encode()
            message_id = PubSubProvider.publish(
                self.config.GCP_PUBSUB_TOPIC_PROCUREMENTS, message_bytes
            )
            self.logger.debug(
                f"Successfully published message {message_id} for {procurement.pncp_control_number}."
            )
            return True
        except exceptions.GoogleAPICallError as e:
            self.logger.error(
                f"Failed to publish message for {procurement.pncp_control_number}: {e}"
            )
            return False
