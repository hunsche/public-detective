"""This module defines the repository for handling procurement data.

It provides the `ProcurementsRepository` class, which is responsible for
interacting with the PNCP (Plataforma Nacional de Contratações Públicas)
API to fetch procurement information and their associated documents. It
also handles the complexities of downloading, extracting, and processing
various types of archived files.
"""

import bz2
import gzip
import io
import json
import lzma
import os
import re
import tarfile
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from datetime import date
from http import HTTPStatus
from typing import Any, cast
from urllib.parse import urljoin
from uuid import UUID

import py7zr
import rarfile
import requests
from google.api_core import exceptions
from public_detective.models.procurements import (
    DocumentType,
    Procurement,
    ProcurementDocument,
    ProcurementListResponse,
    ProcurementModality,
)
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.http import HttpProvider
from public_detective.providers.logging import Logger, LoggingProvider
from public_detective.providers.pubsub import PubSubProvider
from pydantic import BaseModel, ValidationError
from sqlalchemy import Engine, text


class ProcessedFile(BaseModel):
    """Represents a single, processed file ready for analysis.

    Attributes:
        source_document_id: The unique ID of the source `ProcurementDocument`
            from the PNCP API from which this file originated.
        relative_path: The path of the file, relative to its source. For a
            standalone file, this is just the filename. For a file inside an
            archive, it includes the archive's path structure.
        content: The raw byte content of the file.
        raw_document_metadata: The raw JSON dictionary of the source document.
    """

    source_document_id: str
    relative_path: str
    content: bytes
    raw_document_metadata: dict
    extraction_failed: bool = False


class ProcurementsRepository:
    """Manages data operations for procurements.

    This repository handles interactions with the PNCP API to fetch
    procurement data and documents. It also manages the persistence of
    procurement records in the local database.

    Attributes:
        logger: An instance of the application's logger.
        config: The application's configuration object.
        pubsub_provider: A provider for publishing messages to Pub/Sub.
        engine: An SQLAlchemy Engine for database connections.
    """

    _SINGLE_FILE_COMPRESSION_HANDLERS: dict[str, Callable[[bytes], bytes]] = {
        ".gz": gzip.decompress,
        ".bz2": bz2.decompress,
        ".bz": bz2.decompress,
        ".xz": lzma.decompress,
    }
    _TAR_LIKE_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz")

    logger: Logger
    config: Config
    pubsub_provider: PubSubProvider
    engine: Engine
    http_provider: HttpProvider

    def __init__(self, engine: Engine, pubsub_provider: PubSubProvider, http_provider: HttpProvider) -> None:
        """Initializes the repository with its dependencies.

        Args:
            engine: The SQLAlchemy Engine for database connections.
            pubsub_provider: The provider for Pub/Sub messaging.
            http_provider: The provider for HTTP requests.
        """
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.pubsub_provider = pubsub_provider
        self.engine = engine
        self.http_provider = http_provider

    def get_latest_version(self, pncp_control_number: str) -> int:
        """Retrieves the latest version number for a given procurement.

        Args:
            pncp_control_number: The control number of the procurement.

        Returns:
            The highest version number stored for that procurement, or 0 if
            no versions are found.
        """
        sql = text("SELECT MAX(version_number) FROM procurements WHERE pncp_control_number = :pncp_control_number")
        with self.engine.connect() as conn:
            result = conn.execute(sql, {"pncp_control_number": pncp_control_number}).scalar_one_or_none()
        return result or 0

    def get_procurement_by_hash(self, content_hash: str) -> bool:
        """Checks if a procurement with a given content hash already exists.

        This is used for idempotency to avoid re-processing the same version
        of a procurement if its content has not changed.

        Args:
            content_hash: The SHA-256 hash of the procurement's content.

        Returns:
            True if a procurement with the given hash exists, False otherwise.
        """
        sql = text("SELECT 1 FROM procurements WHERE content_hash = :content_hash")
        with self.engine.connect() as conn:
            result = conn.execute(sql, {"content_hash": content_hash}).scalar_one_or_none()
        return result is not None

    def save_procurement_version(
        self, procurement: Procurement, raw_data: str, version_number: int, content_hash: str
    ) -> None:
        """Saves a new version of a procurement to the database.

        Args:
            procurement: The Pydantic model of the procurement.
            raw_data: The raw JSON string of the procurement data.
            version_number: The new version number for this procurement.
            content_hash: The hash of the procurement's content for
                idempotency.
        """
        self.logger.info(
            f"Saving procurement {procurement.pncp_control_number} version {version_number} to the database."
        )
        sql = text(
            """
            INSERT INTO procurements (
                pncp_control_number, proposal_opening_date, proposal_closing_date,
                object_description, total_awarded_value, is_srp, procurement_year,
                procurement_sequence, pncp_publication_date, last_update_date,
                modality_id, procurement_status_id, total_estimated_value,
                version_number, raw_data, content_hash, current_quality_score,
                current_estimated_cost, current_potential_impact_score, current_priority_score, is_stable,
                last_changed_at, temporal_score, federal_bonus_score
            ) VALUES (
                :pncp_control_number, :proposal_opening_date, :proposal_closing_date,
                :object_description, :total_awarded_value, :is_srp, :procurement_year,
                :procurement_sequence, :pncp_publication_date, :last_update_date,
                :modality_id, :procurement_status_id, :total_estimated_value,
                :version_number, :raw_data, :content_hash, :current_quality_score,
                :current_estimated_cost, :current_potential_impact_score, :current_priority_score, :is_stable,
                :last_changed_at, :temporal_score, :federal_bonus_score
            );
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
            "version_number": version_number,
            "raw_data": raw_data,
            "content_hash": content_hash,
            "current_quality_score": procurement.current_quality_score,
            "current_estimated_cost": procurement.current_estimated_cost,
            "current_potential_impact_score": procurement.current_potential_impact_score,
            "current_priority_score": procurement.current_priority_score,
            "is_stable": procurement.is_stable,
            "last_changed_at": procurement.last_changed_at,
            "temporal_score": procurement.temporal_score,
            "federal_bonus_score": procurement.federal_bonus_score,
        }
        with self.engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()
        self.logger.info("Procurement version saved successfully.")

    def get_procurement_by_id_and_version(self, pncp_control_number: str, version_number: int) -> Procurement | None:
        """Retrieves a specific version of a procurement from the database.

        Args:
            pncp_control_number: The control number of the procurement.
            version_number: The specific version to retrieve.

        Returns:
            A `Procurement` object if found, otherwise `None`.
        """
        sql = text(
            """
            SELECT
                raw_data,
                procurement_id,
                votes_count,
                votes_count,
                current_quality_score,
                current_estimated_cost,
                current_potential_impact_score,
                current_priority_score,
                is_stable,
                last_changed_at,
                temporal_score,
                federal_bonus_score,
                version_number
            FROM procurements
            WHERE pncp_control_number = :pncp_control_number
              AND version_number = :version_number
            """
        )

        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    sql,
                    {
                        "pncp_control_number": pncp_control_number,
                        "version_number": version_number,
                    },
                )
                .mappings()
                .one_or_none()
            )

        if row is None:
            return None

        raw_payload = row["raw_data"]
        if isinstance(raw_payload, str):
            raw_data: dict[str, Any] = json.loads(raw_payload)
        else:
            raw_data = dict(raw_payload)

        raw_data["procurement_id"] = row["procurement_id"]
        raw_data["votes_count"] = row["votes_count"]
        raw_data["current_quality_score"] = row["current_quality_score"]
        raw_data["current_estimated_cost"] = row["current_estimated_cost"]
        raw_data["current_potential_impact_score"] = row["current_potential_impact_score"]
        raw_data["current_priority_score"] = row["current_priority_score"]
        raw_data["is_stable"] = row["is_stable"]
        raw_data["last_changed_at"] = row["last_changed_at"]
        raw_data["temporal_score"] = row["temporal_score"]
        raw_data["federal_bonus_score"] = row["federal_bonus_score"]
        raw_data["version_number"] = row["version_number"]

        return Procurement.model_validate(raw_data)

    def get_procurement_uuid(self, pncp_control_number: str, version_number: int) -> UUID | None:
        """Retrieves the UUID for a specific version of a procurement.

        Args:
            pncp_control_number: The control number of the procurement.
            version_number: The specific version to retrieve.

        Returns:
            The procurement's UUID if found, otherwise `None`.
        """
        sql = text(
            "SELECT procurement_id FROM procurements "
            "WHERE pncp_control_number = :pncp_control_number AND version_number = :version_number"
        )
        with self.engine.connect() as conn:
            result = conn.execute(
                sql, {"pncp_control_number": pncp_control_number, "version_number": version_number}
            ).scalar_one_or_none()
        return result

    def update_procurement_ranking_data(self, procurement: Procurement, version_number: int) -> None:
        """Updates the ranking-related fields for an existing procurement.

        Args:
            procurement: The procurement object with updated ranking data.
            version_number: The version of the procurement to update.
        """
        sql = text(
            """
            UPDATE procurements
            SET
                current_quality_score = :current_quality_score,
                current_estimated_cost = :current_estimated_cost,
                current_potential_impact_score = :current_potential_impact_score,
                current_priority_score = :current_priority_score,
                is_stable = :is_stable,
                last_changed_at = :last_changed_at,
                temporal_score = :temporal_score,
                federal_bonus_score = :federal_bonus_score
            WHERE
                pncp_control_number = :pncp_control_number AND
                version_number = :version_number;
            """
        )
        params = {
            "pncp_control_number": procurement.pncp_control_number,
            "version_number": version_number,
            "current_quality_score": procurement.current_quality_score,
            "current_estimated_cost": procurement.current_estimated_cost,
            "current_potential_impact_score": procurement.current_potential_impact_score,
            "current_priority_score": procurement.current_priority_score,
            "is_stable": procurement.is_stable,
            "last_changed_at": procurement.last_changed_at,
            "temporal_score": procurement.temporal_score,
            "federal_bonus_score": procurement.federal_bonus_score,
        }
        with self.engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()

    def get_procurement_by_control_number(self, pncp_control_number: str) -> tuple[Procurement | None, dict | None]:
        """Fetches a single procurement and its raw data by its PNCP control number.

        Args:
            pncp_control_number: The control number of the procurement.

        Returns:
            A tuple containing the parsed `Procurement` model and its raw
            JSON data, or (None, None) if not found or an error occurs.
        """
        try:
            match = re.match(r"(\d{14})-(\d+)-(\d+)/(\d{4})", pncp_control_number)
            if not match:
                self.logger.error(f"Invalid PNCP control number format: {pncp_control_number}")
                return None, None

            cnpj, _, sequence, year = match.groups()

            endpoint = f"orgaos/{cnpj}/compras/{year}/{sequence}"
            api_url = urljoin(self.config.PNCP_PUBLIC_QUERY_API_URL, endpoint)
            response = self.http_provider.get(api_url)
            response.raise_for_status()

            raw_data = response.json()
            try:
                procurement = Procurement.model_validate(raw_data)
                return procurement, raw_data
            except ValidationError as e:
                self.logger.error(f"Procurement data validation failed for {pncp_control_number}: {e}")
                self.logger.debug(f"Raw data received: {raw_data}")
                return None, None
        except (requests.RequestException, ValidationError) as e:
            self.logger.error(f"Failed to get/validate procurement for {pncp_control_number}: {e}")
            return None, None

    def process_procurement_documents(self, procurement: Procurement) -> list[ProcessedFile]:
        """Downloads and processes all documents for a given procurement.

        This method orchestrates the entire document handling pipeline:
        1. Fetches metadata for all associated documents from the PNCP API.
        2. Downloads the content of each document.
        3. Recursively extracts files from any archives (ZIP, RAR, etc.).
        4. Collects all non-archive files into a final list of `ProcessedFile` objects.

        Args:
            procurement: The procurement whose documents are to be processed.

        Returns:
            A list of `ProcessedFile` objects, each containing the file content
            and metadata about its origin.
        """
        documents_to_download = self._get_all_documents_metadata(procurement)
        if not documents_to_download:
            return []

        final_files: list[ProcessedFile] = []

        for doc, raw_doc_metadata in documents_to_download:
            content = self._download_file_content(doc.url)
            if not content:
                continue

            original_filename = self._determine_original_filename(doc.url) or doc.title
            synthetic_document_id = (
                f"{doc.cnpj}-{doc.procurement_year}-" f"{doc.procurement_sequence}-{doc.document_sequence}"
            )

            self._recursive_file_processing(
                source_document_id=synthetic_document_id,
                content=content,
                current_path=original_filename,
                nesting_level=0,
                file_collection=final_files,
                raw_document_metadata=raw_doc_metadata,
            )

        return final_files

    def _recursive_file_processing(
        self,
        source_document_id: str,
        content: bytes,
        current_path: str,
        nesting_level: int,
        file_collection: list[ProcessedFile],
        raw_document_metadata: dict,
    ) -> None:
        """Recursively processes file content, handling nested archives.

        This method checks if the given content is an archive (ZIP, RAR,
        etc.). If it is, it extracts the contents and calls itself for each
        member. If it's not an archive, it adds the content to the final
        `file_collection` as a `ProcessedFile` object.

        Args:
            source_document_id: The ID of the source `ProcurementDocument`.
            content: The byte content of the file to process.
            current_path: The path of the file being processed, including
                any parent archive names.
            nesting_level: The current depth of recursion.
            file_collection: A list where final `ProcessedFile` objects are
                collected.
            raw_document_metadata: The raw JSON dictionary of the source document.
        """
        lower_path = current_path.lower()
        handler = None

        if lower_path.endswith(".zip"):
            handler = self._extract_from_zip
        elif lower_path.endswith(".rar"):
            handler = self._extract_from_rar
        elif lower_path.endswith(".7z"):
            handler = self._extract_from_7z
        elif tarfile.is_tarfile(io.BytesIO(content)):
            handler = self._extract_from_tar

        if handler:
            try:
                nested_files = handler(content)
                for member_name, member_content in nested_files:
                    new_path = os.path.join(current_path, member_name)
                    self._recursive_file_processing(
                        source_document_id=source_document_id,
                        content=member_content,
                        current_path=new_path,
                        nesting_level=nesting_level + 1,
                        file_collection=file_collection,
                        raw_document_metadata=raw_document_metadata,
                    )
            except Exception as e:
                self.logger.warning(
                    "Could not process archive '%s': %s. " "Treating as a single file with extraction flag.",
                    current_path,
                    e,
                )
                file_collection.append(
                    ProcessedFile(
                        source_document_id=source_document_id,
                        relative_path=current_path,
                        content=content,
                        raw_document_metadata=raw_document_metadata,
                        extraction_failed=True,
                    )
                )
            return

        for suffix, decompressor in self._SINGLE_FILE_COMPRESSION_HANDLERS.items():
            if lower_path.endswith(suffix) and not any(
                lower_path.endswith(tar_suffix) for tar_suffix in self._TAR_LIKE_SUFFIXES
            ):
                try:
                    decompressed_content = decompressor(content)
                except Exception as e:
                    self.logger.warning(
                        "Could not decompress single-file archive '%s': %s. "
                        "Treating as a single file with extraction flag.",
                        current_path,
                        e,
                    )
                    file_collection.append(
                        ProcessedFile(
                            source_document_id=source_document_id,
                            relative_path=current_path,
                            content=content,
                            raw_document_metadata=raw_document_metadata,
                            extraction_failed=True,
                        )
                    )
                    return

                stripped_path = current_path[: -len(suffix)] or f"{current_path}_decompressed"
                self._recursive_file_processing(
                    source_document_id=source_document_id,
                    content=decompressed_content,
                    current_path=stripped_path,
                    nesting_level=nesting_level + 1,
                    file_collection=file_collection,
                    raw_document_metadata=raw_document_metadata,
                )
                return

        file_collection.append(
            ProcessedFile(
                source_document_id=source_document_id,
                relative_path=current_path,
                content=content,
                raw_document_metadata=raw_document_metadata,
                extraction_failed=False,
            )
        )

    def create_zip_from_files(self, files: list[tuple[str, bytes]], control_number: str) -> bytes | None:
        """Creates a single, flat ZIP archive in memory from a list of files.

        Args:
            files: A list of tuples, where each tuple contains the file path
                and its byte content.
            control_number: The procurement control number, used for logging.

        Returns:
            The byte content of the generated ZIP archive, or `None` if the
            input list was empty or an error occurred.
        """
        if not files:
            return None
        self.logger.info(f"Creating final ZIP archive with {len(files)} files for " f"{control_number}...")
        zip_stream = io.BytesIO()
        try:
            with zipfile.ZipFile(zip_stream, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file_path, content in files:
                    safe_path = re.sub(r'[<>:"/\\|?*]', "_", file_path)
                    zip_file.writestr(safe_path, content)
            zip_bytes = zip_stream.getvalue()
            self.logger.info(f"Successfully created final ZIP archive of {len(zip_bytes)} bytes.")
            return zip_bytes
        except Exception as e:
            self.logger.error(f"Failed to create final ZIP archive for {control_number}: {e}")
            return None

    def _extract_from_zip(self, content: bytes) -> list[tuple[str, bytes]]:
        """Extracts all members from a ZIP archive in memory.

        Args:
            content: The byte content of the ZIP file.

        Returns:
            A list of tuples, each containing the filename and byte content
            of a member file.
        """
        extracted = []
        with io.BytesIO(content) as stream:
            with zipfile.ZipFile(stream, strict_timestamps=False) as archive:
                for member_info in archive.infolist():
                    if member_info.is_dir():
                        continue
                    try:
                        extracted.append((member_info.filename, archive.read(member_info)))
                    except ValueError as error:
                        self.logger.warning(
                            "Failed to extract member '%s' from ZIP archive: %s", member_info.filename, error
                        )
                        raise
        return extracted

    def _extract_from_rar(self, content: bytes) -> list[tuple[str, bytes]]:
        """Extracts all members from a RAR archive in memory.

        Args:
            content: The byte content of the RAR file.

        Returns:
            A list of tuples, each containing the filename and byte content
            of a member file. Returns an empty list if the archive is invalid.
        """
        extracted = []
        try:
            with io.BytesIO(content) as stream:
                with rarfile.RarFile(stream) as archive:
                    for member_info in archive.infolist():
                        if member_info.isdir():
                            continue
                        try:
                            extracted.append((member_info.filename, archive.read(member_info.filename)))
                        except rarfile.Error as error:
                            self.logger.warning(
                                "Failed to read member '%s' from RAR archive: %s", member_info.filename, error
                            )
                            raise RuntimeError(
                                f"Failed to read member '{member_info.filename}' from RAR archive"
                            ) from error
        except rarfile.BadRarFile as error:
            self.logger.warning("Failed to extract from a corrupted or invalid RAR file: %s", error)
            raise RuntimeError("Failed to extract from RAR archive") from error
        except rarfile.NeedPassword as error:
            self.logger.warning("Cannot extract password-protected RAR archive: %s", error)
            raise RuntimeError("Password-protected RAR archives are not supported") from error
        except rarfile.Error as error:
            self.logger.warning("Unexpected RAR extraction error: %s", error)
            raise RuntimeError("Unexpected RAR extraction error") from error
        return extracted

    def _extract_from_7z(self, content: bytes) -> list[tuple[str, bytes]]:
        """Extracts all members from a 7z archive in memory.

        This method writes the content to a temporary directory to perform the
        extraction, as `py7zr` works most reliably with file paths.

        Args:
            content: The byte content of the 7z file.

        Returns:
            A list of tuples, each containing the filename and byte content
            of a member file.
        """
        extracted = []
        with tempfile.TemporaryDirectory() as tmpdir:
            with io.BytesIO(content) as stream:
                with py7zr.SevenZipFile(stream, mode="r", mp=False) as archive:
                    archive.extractall(path=tmpdir)

            for root, _, files in os.walk(tmpdir):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    try:
                        with open(filepath, "rb") as file:
                            file_content = file.read()
                    except PermissionError:
                        os.chmod(filepath, 0o644)
                        with open(filepath, "rb") as file:
                            file_content = file.read()
                    relative_path = os.path.relpath(filepath, tmpdir)
                    extracted.append((relative_path, file_content))
        return extracted

    def _extract_from_tar(self, content: bytes) -> list[tuple[str, bytes]]:
        """Extracts all members from a TAR archive in memory.

        This method can handle various TAR compressions like .gz and .bz2.

        Args:
            content: The byte content of the TAR file.

        Returns:
            A list of tuples, each containing the filename and byte content
            of a member file.
        """
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

    def _get_all_documents_metadata(self, procurement: Procurement) -> list[tuple[ProcurementDocument, dict]]:
        """Fetches metadata for all of a procurement's documents from the API.

        This method retrieves the list of all documents associated with a
        given procurement, filters for active ones, and then sorts them to
        prioritize the 'BID_NOTICE' document type, as it is often the most
        important.

        Args:
            procurement: The procurement for which to fetch document metadata.

        Returns:
            A list of tuples, where each tuple contains the parsed `ProcurementDocument`
            model and its raw JSON data. Returns an empty list if an error occurs.
        """
        try:
            endpoint = (
                f"orgaos/{procurement.government_entity.cnpj}/compras/"
                f"{procurement.procurement_year}/{procurement.procurement_sequence}/arquivos"
            )
            api_url = urljoin(self.config.PNCP_INTEGRATION_API_URL, endpoint)
            response = self.http_provider.get(api_url)
            if response.status_code == HTTPStatus.NO_CONTENT:
                return []
            response.raise_for_status()
            raw_docs = response.json()

            all_docs = [(ProcurementDocument.model_validate(doc), doc) for doc in raw_docs]
            active_docs = [(doc, raw) for doc, raw in all_docs if doc.is_active]

            if len(active_docs) < len(all_docs):
                self.logger.info(f"Filtered out {len(all_docs) - len(active_docs)} inactive documents.")

            active_docs.sort(key=lambda item: item[0].document_type_id != DocumentType.BID_NOTICE)
            self.logger.info(f"Found metadata for {len(active_docs)} active document(s).")
            return active_docs
        except (requests.RequestException, ValidationError) as e:
            self.logger.error(f"Failed to get/validate document list for {procurement.pncp_control_number}: {e}")
            return []

    def _download_file_content(self, url: str) -> bytes | None:
        """Downloads the binary content of a file from a URL.

        Args:
            url: The URL of the file to download.

        Returns:
            The byte content of the file, or `None` if the download fails.
        """
        try:
            response = self.http_provider.get(url, timeout=90)
            response.raise_for_status()
            if response.content:
                return cast(bytes, response.content)
            return None
        except requests.RequestException as e:
            self.logger.error(f"Failed to download content from {url}: {e}")
            return None

    def _determine_original_filename(self, url: str) -> str | None:
        """Determines a file's original name from the Content-Disposition header.

        This method makes a HEAD request to the file's URL to efficiently
        check the `Content-Disposition` header without downloading the entire
        file.

        Args:
            url: The URL of the file.

        Returns:
            The original filename if found in the header, otherwise `None`.
        """
        try:
            response = self.http_provider.head(url, allow_redirects=True)
            response.raise_for_status()
            content_disposition = response.headers.get("Content-Disposition")
            if content_disposition:
                match = re.search(r'filename="?([^"+]+)"?', content_disposition, re.IGNORECASE)
                if match:
                    return match.group(1)
        except requests.RequestException as e:
            self.logger.warning(f"Could not determine filename from headers for {url}: {e}")
        return None

    def get_updated_procurements(self, target_date: date) -> list[Procurement]:
        """Fetches all procurements updated on a specific date.

        This method queries the PNCP API for all procurements that were
        updated on the given date. It iterates through a predefined list of
        relevant modalities and all configured IBGE city codes to build a
        comprehensive list.

        Args:
            target_date: The specific date to query for updates.

        Returns:
            A list of `Procurement` objects.
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
            codes_to_check = [None]
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
                        response = self.http_provider.get(
                            urljoin(self.config.PNCP_PUBLIC_QUERY_API_URL, endpoint),
                            params=params,
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
                    except requests.RequestException as e:
                        self.logger.error(f"Error fetching updates on page {page}: {e}")
                        break
                    except ValidationError as e:
                        self.logger.error(f"Data validation error on page {page}: {e}")
                        break
        self.logger.info(f"Finished fetching. Total procurements: {len(all_procurements)}")
        return all_procurements

    def get_updated_procurements_with_raw_data(
        self, target_date: date
    ) -> Iterator[tuple[str, Any | tuple[Procurement, dict]]]:
        """Fetches updated procurements with raw data as a generator.

        This method queries the PNCP API for procurements updated on a specific
        date. It yields events to report progress, such as when a modality
        search begins, the total number of pages found, and each batch of
        procurements as it is fetched.

        Args:
            target_date: The date to query for procurement updates.

        Yields:
            Tuples representing different stages of the fetching process:
            - ("modality_started", modality_name): Indicates the start of
              fetching for a new procurement modality.
            - ("pages_total", total_pages): Provides the total number of pages
              to be fetched for the current modality.
            - ("procurements_page", (procurement, raw_data)): Yields a tuple
              containing a `Procurement` object and its raw JSON data.
        """
        modalities_to_check = [
            ProcurementModality.ELECTRONIC_REVERSE_AUCTION,
            ProcurementModality.BIDDING_WAIVER,
            ProcurementModality.BIDDING_UNENFORCEABILITY,
            ProcurementModality.ELECTRONIC_COMPETITION,
        ]
        self.logger.info(f"Fetching all procurements updated on {target_date} with raw data...")
        codes_to_check = self.config.TARGET_IBGE_CODES
        if not codes_to_check:
            self.logger.warning("No TARGET_IBGE_CODES configured. The search will be nationwide.")
            codes_to_check = [None]
        for city_code in codes_to_check:
            if city_code:
                self.logger.info(f"Searching for city with IBGE code: {city_code}")
            for modality in modalities_to_check:
                yield "modality_started", modality.name
                page = 1
                total_pages = 1
                while page <= total_pages:
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
                        api_url = urljoin(self.config.PNCP_PUBLIC_QUERY_API_URL, endpoint)
                        response = self.http_provider.get(api_url, params=params)
                        if response.status_code == HTTPStatus.NO_CONTENT:
                            break
                        response.raise_for_status()
                        raw_json = response.json()
                        parsed_data = ProcurementListResponse.model_validate(raw_json)
                        if page == 1:
                            total_pages = parsed_data.total_pages
                            yield "pages_total", total_pages
                        if not parsed_data.data:
                            break
                        for i, procurement_model in enumerate(parsed_data.data):
                            yield "procurements_page", (procurement_model, raw_json["data"][i])
                        yield "page_fetched", page
                        page += 1
                    except requests.RequestException as e:
                        self.logger.error(f"Error fetching updates on page {page}: {e}")
                        break
                    except ValidationError as e:
                        self.logger.error(f"Data validation error on page {page}: {e}")
                        break

    def publish_procurement_to_pubsub(self, procurement: Procurement) -> bool:
        """Publishes a procurement object to the configured Pub/Sub topic.

        Args:
            procurement: The `Procurement` object to publish.

        Returns:
            True if the message was published successfully, False otherwise.
        """
        try:
            message_json = procurement.model_dump_json(by_alias=True)
            message_bytes = message_json.encode()
            message_id = self.pubsub_provider.publish(self.config.GCP_PUBSUB_TOPIC_PROCUREMENTS, message_bytes)
            self.logger.debug(f"Successfully published message {message_id} for " f"{procurement.pncp_control_number}.")
            return True
        except exceptions.GoogleAPICallError as e:
            self.logger.error(f"Failed to publish message for {procurement.pncp_control_number}: {e}")
            return False
