"""This module provides a generic interface to interact with a Google's AI.

It defines a generic `AiProvider` class that can be specialized with a
Pydantic model to handle structured data output from the AI. The provider
manages API configuration, prompt execution, and robust parsing of the AI's
response based on GCS URIs.
"""

import json
from mimetypes import guess_type
from typing import Generic, TypeVar

import vertexai
from pydantic import BaseModel, ValidationError
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider
from vertexai.generative_models import GenerationConfig, GenerativeModel, Part

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class AiProvider(Generic[PydanticModel]):
    """
    Provides a generic interface to interact with the Google Gemini AI model via Vertex AI,
    specialized for a specific Pydantic output model.
    """

    def __init__(self, output_schema: type[PydanticModel]):
        """
        Initializes the AiProvider, configuring the Vertex AI client for a specific
        output schema.

        Args:
            output_schema: The Pydantic model class that this provider instance
                           will use for all structured outputs.
        """
        self.logger: Logger = LoggingProvider().get_logger()
        self.config: Config = ConfigProvider.get_config()
        self.output_schema: type[PydanticModel] = output_schema

        try:
            vertexai.init(project=self.config.GCP_PROJECT, location="us-central1")
            self.model: GenerativeModel = GenerativeModel(self.config.GCP_GEMINI_MODEL)
            self.logger.info(
                f"Vertex AI client configured successfully for model '{self.config.GCP_GEMINI_MODEL}' "
                f"and schema '{self.output_schema.__name__}'."
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize Vertex AI: {e}", exc_info=True)
            raise ValueError("Failed to initialize Vertex AI. Ensure credentials are set up correctly.") from e

    def get_structured_analysis(
        self, prompt: str, gcs_uris: list[str], max_output_tokens: int | None = None
    ) -> tuple[PydanticModel, int, int]:
        """
        Sends a prompt and a list of GCS URIs for analysis and parses the
        structured response into the Pydantic model instance defined for this provider.

        Args:
            prompt: The instructional prompt for the AI model.
            gcs_uris: A list of GCS URIs (e.g., 'gs://bucket/file.pdf') pointing to the files.
            max_output_tokens: An optional integer to set the token limit.

        Returns:
            A tuple containing the Pydantic model instance, input tokens, and output tokens.
        """
        self.logger.info(f"Sending request to Vertex AI for {len(gcs_uris)} GCS files.")
        file_parts = []
        for uri in gcs_uris:
            mime_type = guess_type(uri)[0] or "application/octet-stream"
            file_parts.append(Part.from_uri(uri=uri, mime_type=mime_type))

        contents = [prompt, *file_parts]
        schema_dict = self.output_schema.model_json_schema()

        generation_config = GenerationConfig(
            response_schema=schema_dict,
            response_mime_type="application/json",
            max_output_tokens=max_output_tokens or self.config.GCP_GEMINI_MAX_OUTPUT_TOKENS,
        )

        response = self.model.generate_content(contents, generation_config=generation_config)
        self.logger.debug("Successfully received response from Vertex AI API.")

        validated_response = self._parse_and_validate_response(response)
        input_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count

        return validated_response, input_tokens, output_tokens

    def count_tokens_for_analysis(self, prompt: str, files: list[tuple[str, bytes]]) -> tuple[int, int]:
        """
        Calculates the number of tokens for a given prompt and list of files.
        Note: This method uses file bytes directly, as it's used in a pre-analysis
        step before files are uploaded to GCS.

        Args:
            prompt: The instructional prompt for the AI model.
            files: A list of tuples containing the file display name and its byte content.

        Returns:
            A tuple containing the total number of input tokens and 0 for output tokens.
        """
        self.logger.info("Counting tokens for analysis (from bytes)...")
        parts = [prompt]
        for file_display_name, file_content in files:
            mime_type = guess_type(file_display_name)[0] or "application/octet-stream"
            parts.append(Part.from_data(data=file_content, mime_type=mime_type))

        response = self.model.count_tokens(parts)
        token_count = response.total_tokens
        self.logger.info(f"Estimated token count: {token_count}")
        return token_count, 0

    def _parse_and_validate_response(self, response: "GenerateContentResponse") -> PydanticModel:
        """Parses the AI's response, handling multiple potential formats and errors."""
        if not response.candidates:
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason.name
                self.logger.error(f"Vertex AI API blocked the prompt. Reason: {block_reason}")
                raise ValueError(f"AI model blocked the response due to: {block_reason}")

            self.logger.error(f"Vertex AI API returned no candidates. Full response: {response}")
            raise ValueError("AI model returned an empty response.")

        try:
            text_content = response.text
            self.logger.debug(f"Received text response from Vertex AI: {text_content}")
            if text_content.strip().startswith("```json"):
                text_content = text_content.strip()[7:-3]

            json_data = json.loads(text_content)
            self.logger.info("Successfully parsed JSON data from text response.")
            return self.output_schema.model_validate(json_data)

        except (json.JSONDecodeError, ValidationError) as e:
            self.logger.warning(f"Failed to parse JSON from text response, trying function call. Error: {e}")

        try:
            function_call = response.candidates[0].content.parts[0].function_call
            if function_call and function_call.name == self.output_schema.__name__:
                self.logger.info("Successfully found structured data in function_call.")
                return self.output_schema.model_validate(function_call.args)

            self.logger.error(f"No valid JSON or function call found. Full API Response: {response}")
            raise ValueError("AI model returned a response that could not be parsed.")

        except (AttributeError, IndexError, ValidationError) as e:
            self.logger.error(f"Failed to parse or validate the AI's response: {e}", exc_info=True)
            self.logger.error(f"Full API Response: {response}")
            raise ValueError(
                "AI model returned a response that could not be parsed into the " "expected structure."
            ) from e
