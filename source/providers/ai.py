"""This module provides a generic interface to interact with a Google's AI.

It defines a generic `AiProvider` class that can be specialized with a
Pydantic model to handle structured data output from the AI. The provider
manages API configuration, file uploads, prompt execution, and robust parsing
of the AI's response.
"""

import json
import os
from mimetypes import guess_type
from typing import Generic, TypeVar
from uuid import uuid4

import vertexai
from google.cloud import aiplatform
from providers.config import Config, ConfigProvider
from providers.gcs import GcsProvider
from providers.logging import Logger, LoggingProvider
from pydantic import BaseModel, ValidationError
from vertexai.generative_models import Content, GenerationConfig, GenerationResponse, GenerativeModel, Part

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class AiProvider(Generic[PydanticModel]):
    """Provides a generic interface to interact with the Google Gemini AI model.

    This class is specialized for a specific Pydantic output model.
    """

    logger: Logger
    config: Config
    model: GenerativeModel
    gcs_provider: GcsProvider
    output_schema: type[PydanticModel]

    def __init__(self, output_schema: type[PydanticModel]):
        """Initializes the AiProvider.

        This method configures the Gemini client for a specific output schema.

        Args:
            output_schema: The Pydantic model class that this provider instance
                           will use for all structured outputs.


        """
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.output_schema = output_schema
        self.gcs_provider = GcsProvider()

        emulator_host = self.config.GCP_AI_HOST
        credentials_value = self.config.GCP_SERVICE_ACCOUNT_CREDENTIALS
        credentials = None

        # Priority 1: Use Emulator if GCP_AI_HOST is set
        if emulator_host:
            self.logger.info(f"AI client configured for emulator at {emulator_host}")
            # The aiplatform.init() function will automatically use this env var
            os.environ["AIPLATFORM_EMULATOR_HOST"] = str(emulator_host)
        # Priority 2: Use Service Account JSON from env var
        elif credentials_value:
            try:
                if credentials_value.strip().startswith("{"):
                    self.logger.info("AI client configured from Service Account JSON string.")
                    credentials_info = json.loads(credentials_value)
                    from google.oauth2 import service_account

                    credentials = service_account.Credentials.from_service_account_info(credentials_info)
                else:
                    raise ValueError(
                        "GCP_SERVICE_ACCOUNT_CREDENTIALS is set but does not appear to be a JSON object."
                    )
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse GCP credentials JSON: {e}")
                raise ValueError("Invalid JSON in GCP_SERVICE_ACCOUNT_CREDENTIALS.") from e
        # Priority 3: Fallback to Application Default Credentials (credentials=None)
        else:
            self.logger.info("AI client configured for Google Cloud production via Application Default Credentials.")

        aiplatform.init(
            project=self.config.GCP_PROJECT,
            location=self.config.GCP_LOCATION,
            credentials=credentials,
        )
        vertexai.init(project=self.config.GCP_PROJECT, location=self.config.GCP_LOCATION, credentials=credentials)

        self.model = GenerativeModel(self.config.GCP_GEMINI_MODEL)
        self.logger.info(
            "Google Vertex AI client configured successfully for schema " f"'{self.output_schema.__name__}'."
        )

    def get_structured_analysis(
        self, prompt: str, files: list[tuple[str, bytes]], max_output_tokens: int | None = None
    ) -> tuple[PydanticModel, int, int]:
        """Uploads a file, sends it for analysis, and parses the response.

        This method is designed to be highly robust, handling cases where the AI
        response might be empty, blocked by safety settings, or returned in

        Args:
            prompt: The instructional prompt for the AI model.
            files: A list of tuples:
                - A list of tuples with file paths and their byte content.
                - A list of descriptive names for the uploaded files.
            max_output_tokens: An optional integer to set the token limit.
                If `None`, no limit is applied.

        Returns:
            A tuple containing:
            - An instance of the Pydantic model associated with this provider,
              populated with the AI's response.
            - The number of input tokens used.
            - The number of output tokens used.
        """
        file_parts = []
        for file_display_name, file_content in files:
            self.logger.info(f"Uploading '{file_display_name}' to GCS.")
            gcs_uri = self._upload_file_to_gcs(file_content, file_display_name)
            mime_type = guess_type(file_display_name)[0]
            file_parts.append(Part.from_uri(gcs_uri, mime_type=mime_type))

        contents = [prompt, *file_parts]
        # The response schema is explicitly defined here to ensure all fields are
        # treated as required by the AI model, avoiding potential issues with
        # optional fields in the Pydantic model.
        ai_schema = {
            "type": "object",
            "properties": {
                "risk_score": {"type": "integer"},
                "risk_score_rationale": {"type": "string"},
                "procurement_summary": {"type": "string"},
                "analysis_summary": {"type": "string"},
                "red_flags": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "description": {"type": "string"},
                            "evidence_quote": {"type": "string"},
                            "auditor_reasoning": {"type": "string"},
                        },
                        "required": ["category", "description", "evidence_quote", "auditor_reasoning"],
                    },
                },
                "seo_keywords": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "risk_score",
                "risk_score_rationale",
                "procurement_summary",
                "analysis_summary",
                "red_flags",
                "seo_keywords",
            ],
        }

        generation_config = GenerationConfig(
            response_mime_type="application/json",
            max_output_tokens=max_output_tokens,
            response_schema=ai_schema,
        )

        response = self.model.generate_content(contents, generation_config=generation_config)
        self.logger.debug("Successfully received response from Vertex AI API.")

        validated_response = self._parse_and_validate_response(response)
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count

        return validated_response, input_tokens, output_tokens

    def count_tokens_for_analysis(self, prompt: str, files: list[tuple[str, bytes]]) -> tuple[int, int]:
        """Calculates the number of tokens for a given prompt and files.

        Args:
            prompt: The instructional prompt for the AI model.
            files: A list of tuples, where each tuple contains:
                - The file path (for display name and mime type guessing).
                - The byte content of the file.

        Returns:
            A tuple containing the total number of input tokens and 0 for output tokens.
        """
        self.logger.info("Counting tokens for analysis...")
        file_parts = []
        for file_display_name, file_content in files:
            mime_type = guess_type(file_display_name)[0]
            if not mime_type:
                mime_type = "application/octet-stream"
            file_parts.append(Part.from_data(file_content, mime_type=mime_type))

        contents = [prompt, *file_parts]
        response = self.model.count_tokens(contents)
        token_count = response.total_tokens
        self.logger.info(f"Estimated token count: {token_count}")
        return token_count, 0

    def _parse_and_validate_response(self, response: GenerationResponse) -> PydanticModel:
        """Parses the AI's response, handling multiple potential formats and errors.

        This method provides a robust, multi-step process to extract and validate
        the structured data from the model's response.

        Args:
            response: The complete response object from the `generate_content` call.

        Returns:
            A validated Pydantic model instance.

        Raises:
            ValueError: If the response is empty, blocked, or unparsable.
        """
        if not response.candidates:
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason.name
                self.logger.error(f"Vertex AI API blocked the prompt. Reason: {block_reason}")
                raise ValueError(f"AI model blocked the response due to: {block_reason}")

            self.logger.error(f"Vertex AI API returned no candidates. Full response: {response}")
            raise ValueError("AI model returned an empty response.")

        try:
            # In Vertex AI, the structured response is directly in the .text attribute
            # when a schema is provided.
            response_text = response.text
            self.logger.debug(f"Received text response from Vertex AI: {response_text}")
            if response_text.strip().startswith("```json"):
                response_text = response_text.strip()[7:-3]
            json_data = json.loads(response_text)
            self.logger.info("Successfully parsed JSON data from text response.")
            return self.output_schema.model_validate(json_data)

        except (json.JSONDecodeError, ValidationError) as e:
            self.logger.error(f"Failed to parse or validate the AI's response: {e}")
            self.logger.error(f"Full API Response: {response}")
            raise ValueError(
                "AI model returned a response that could not be parsed into the " "expected structure."
            ) from e

    def _upload_file_to_gcs(self, content: bytes, display_name: str) -> str:
        """Uploads file content to GCS and returns the GCS URI.

        Args:
            content: The raw byte content of the file to be uploaded.
            display_name: The name of the file, used to determine content type
                          and the object name in GCS.

        Returns:
            The GCS URI of the uploaded file (e.g., gs://bucket-name/object-name).
        """
        bucket_name = self.config.GCP_VERTEX_AI_BUCKET
        # Create a unique name for the object in GCS
        object_name = f"ai-uploads/{uuid4()}/{display_name}"
        content_type = guess_type(display_name)[0] or "application/octet-stream"

        self.gcs_provider.upload_file(
            bucket_name=bucket_name,
            destination_blob_name=object_name,
            content=content,
            content_type=content_type,
        )

        gcs_uri = f"gs://{bucket_name}/{object_name}"
        self.logger.info(f"File uploaded to {gcs_uri}")
        return gcs_uri
