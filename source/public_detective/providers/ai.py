"""This module provides a generic interface to interact with a Google's AI.

It defines a generic `AiProvider` class that can be specialized with a
Pydantic model to handle structured data output from the AI. The provider
manages API configuration, file uploads, prompt execution, and robust parsing
of the AI's response.
"""

import json
from mimetypes import guess_type
from typing import Generic, TypeVar
from uuid import uuid4

from google import genai
from google.genai import types
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.logging import Logger, LoggingProvider
from pydantic import BaseModel, ValidationError

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class AiProvider(Generic[PydanticModel]):
    """Provides a generic interface to interact with the Google Gemini AI model.

    This class is specialized for a specific Pydantic output model.
    """

    logger: Logger
    config: Config
    client: genai.Client
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

        self.client = genai.Client(vertexai=True, project=self.config.GCP_PROJECT, location=self.config.GCP_LOCATION)

        self.logger.info(
            "Google Generative AI client configured successfully for schema "
            f"'{self.output_schema.__name__}' using Vertex AI backend."
        )

    def get_structured_analysis(
        self, prompt: str, files: list[tuple[str, bytes]], max_output_tokens: int | None = None
    ) -> tuple[PydanticModel, int, int]:
        """Sends a file for analysis and parses the response.

        This method is designed to be highly robust, handling cases where the AI
        response might be empty, blocked by safety settings, or returned in a
        format that doesn't match the expected Pydantic schema.

        Args:
            prompt: The instructional prompt for the AI model.
            files: A list of tuples, where each tuple contains:
                - The file path (for display name and mime type guessing).
                - The byte content of the file.
            max_output_tokens: An optional integer to set the token limit.
                If `None`, no limit is applied.

        Returns:
            A tuple containing:
            - An instance of the Pydantic model associated with this provider,
              populated with the AI's response.
            - The number of input tokens used.
            - The number of output tokens used.
        """
        file_parts: list[types.Part] = []
        for file_display_name, file_content in files:
            gcs_uri = self._upload_file_to_gcs(file_content, file_display_name)
            mime_type = guess_type(file_display_name)[0] or "application/octet-stream"
            file_parts.append(types.Part.from_uri(file_uri=gcs_uri, mime_type=mime_type))

        all_parts = [types.Part(text=prompt), *file_parts]
        contents = types.Content(role="user", parts=all_parts)

        response = self.client.models.generate_content(
            model=self.config.GCP_GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=self.output_schema,
                max_output_tokens=max_output_tokens,
            ),
        )
        self.logger.debug("Successfully received response from Generative AI API.")

        validated_response = self._parse_and_validate_response(response)
        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

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
        file_parts: list[types.Part] = []
        for file_display_name, file_content in files:
            gcs_uri = self._upload_file_to_gcs(file_content, file_display_name)
            mime_type = guess_type(file_display_name)[0]
            if not mime_type:
                mime_type = "application/octet-stream"
            file_parts.append(types.Part.from_uri(file_uri=gcs_uri, mime_type=mime_type))

        all_parts = [types.Part(text=prompt), *file_parts]
        contents = types.Content(role="user", parts=all_parts)
        response = self.client.models.count_tokens(model=self.config.GCP_GEMINI_MODEL, contents=contents)
        token_count = response.total_tokens
        self.logger.info(f"Estimated token count: {token_count}")
        return token_count or 0, 0

    def _parse_and_validate_response(self, response) -> PydanticModel:  # type: ignore
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
                self.logger.error(f"Generative AI API blocked the prompt. Reason: {block_reason}")
                raise ValueError(f"AI model blocked the response due to: {block_reason}")

            self.logger.error(f"Generative AI API returned no candidates. Full response: {response}")
            raise ValueError("AI model returned an empty response.")

        try:
            response_text = response.text
            self.logger.debug(f"Received text response from Generative AI: {response_text}")
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
        bucket_name = self.config.GCP_GCS_BUCKET_PROCUREMENTS

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
