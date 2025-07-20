from datetime import date
from http import HTTPStatus
from urllib.parse import urljoin

import requests
from google.api_core import exceptions
from google.cloud import pubsub_v1
from models.procurement import Procurement, ProcurementListResponse, ProcurementModality
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider
from providers.pubsub import PubSubProvider
from pydantic import ValidationError


class ProcurementRepository:
    """
    Repository responsible for fetching procurement data from the PNCP API
    and publishing it to a message queue for further processing.
    """

    logger: Logger
    config: Config
    publisher: pubsub_v1.PublisherClient | None
    topic_path: str | None

    def __init__(self):
        """
        Initializes the repository by injecting a logger and loading configuration.
        """
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()

    def get_updated_procurements(self, target_date: date) -> list[Procurement]:
        """
        Fetches all procurements updated on a specific date by iterating
        through relevant modalities and configured city codes (IBGE).
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
                self.logger.info(
                    f"Fetching updates for modality: {modality.name} (Code: {modality.value})"
                )
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
                        self.logger.error(
                            f"Error fetching updates for modality {modality.name} on page {page}: {e}"
                        )
                        break
                    except ValidationError as e:
                        self.logger.error(
                            f"Data validation error for modality {modality.name} on page {page}: {e}"
                        )
                        break

        self.logger.info(
            f"Finished fetching. Total procurements collected: {len(all_procurements)}"
        )
        return all_procurements

    def publish_procurement_to_pubsub(self, procurement: Procurement) -> bool:
        """
        Publishes a procurement object to the configured Google Cloud Pub/Sub topic.

        :param procurement: A Pydantic Procurement model instance.
        :return: True if published successfully, False otherwise.
        """
        try:
            message_json = procurement.model_dump_json()
            message_bytes = message_json.encode()

            message_id = PubSubProvider.publish(
                self.config.GCP_PUBSUB_TOPIC_PROCUREMENTS, message_bytes
            )

            self.logger.debug(
                f"Successfully published message {message_id} for procurement {procurement.pncp_control_number}."
            )
            return True
        except exceptions.GoogleAPICallError as e:
            self.logger.error(
                f"Failed to publish message for procurement {procurement.pncp_control_number}: {e}"
            )
            return False
