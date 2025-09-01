"""This module provides a generic interface to interact with a Google's AI.

It defines a generic `AiProvider` class that can be specialized with a
Pydantic model to handle structured data output from the AI. The provider
manages API configuration, file uploads, prompt execution, and robust parsing
of the AI's response.
"""

import io
import json
import time
from mimetypes import guess_type
from typing import Generic, TypeVar

import google.generativeai as genai
from google.generativeai.types import File
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider
from pydantic import BaseModel, ValidationError

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class AiProvider(Generic[PydanticModel]):
    """
    Provides a generic interface to interact with the Google Gemini AI model,
    specialized for a specific Pydantic output model.
    """

    logger: Logger
    config: Config
    model: genai.GenerativeModel
    output_schema: type[PydanticModel]

    def __init__(self, output_schema: type[PydanticModel]):
        """
        Initializes the AiProvider, configuring the Gemini client for a specific
        output schema.

        Args:
            output_schema: The Pydantic model class that this provider instance
                           will use for all structured outputs.
        """
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.output_schema = output_schema

        if not self.config.GCP_GEMINI_API_KEY:
            self.logger.error("GCP_GEMINI_API_KEY is missing. The AI provider cannot be initialized.")
            raise ValueError("GCP_GEMINI_API_KEY must be configured to use the AI provider.")

        genai.configure(api_key=self.config.GCP_GEMINI_API_KEY)
        self.model = genai.GenerativeModel(self.config.GCP_GEMINI_MODEL)
        self.logger.info("Google Gemini client configured successfully for schema " f"'{self.output_schema.__name__}'.")

    def get_structured_analysis(
        self, prompt: str, files: list[tuple[str, bytes]], max_output_tokens: int | None = None
    ) -> tuple[PydanticModel, int, int]:
        """
        Uploads a file, sends it with a prompt for analysis, and parses the
        structured response into the Pydantic model instance defined for this provider.

        This method is designed to be highly robust, handling cases where the AI
        response might be empty, blocked by safety settings, or returned in
        an unexpected format.

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

        Raises:
            ValueError: If the AI model returns a blocked, empty, or
                        unparsable response.
        """
        uploaded_files = []
        for file in files:
            file_display_name = file[0]
            file_content = file[1]
            self.logger.info(f"Sending request to Gemini API for '{file_display_name}'.")
            uploaded_files.append(self._upload_file_to_gemini(file_content, file_display_name))

        try:
            contents = [prompt, *uploaded_files]
            if max_output_tokens is not None:
                self.logger.info(f"Using max_output_tokens: {max_output_tokens}")
                generation_config = genai.types.GenerationConfig(
                    response_schema=self.output_schema,
                    response_mime_type="application/json",
                    max_output_tokens=max_output_tokens,
                )
            else:
                self.logger.info("max_output_tokens is None, so no limit will be applied.")
                generation_config = genai.types.GenerationConfig(
                    response_schema=self.output_schema,
                    response_mime_type="application/json",
                )

            response = self.model.generate_content(contents, generation_config=generation_config)
            self.logger.debug("Successfully received response from Gemini API.")

            validated_response = self._parse_and_validate_response(response)
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count

            return validated_response, input_tokens, output_tokens

        finally:
            for uploaded_file in uploaded_files:
                self.logger.info(f"Deleting uploaded file: {uploaded_file.name}")
                genai.delete_file(uploaded_file.name)

    def count_tokens_for_analysis(self, prompt: str, files: list[tuple[str, bytes]]) -> tuple[int, int]:
        """
        Calculates the number of tokens for a given prompt and list of files
        without making a call to generate content.

        Args:
            prompt: The instructional prompt for the AI model.
            files: A list of tuples, where each tuple contains:
                - The file path (for display name and mime type guessing).
                - The byte content of the file.

        Returns:
            A tuple containing the total number of input tokens and 0 for output tokens.
        """
        self.logger.info("Counting tokens for analysis...")
        parts: list[str | dict] = [prompt]
        for file_path, file_content in files:
            mime_type = guess_type(file_path)[0]
            if not mime_type:
                mime_type = "application/octet-stream"
            parts.append({"mime_type": mime_type, "data": file_content})

        response = self.model.count_tokens(parts)
        token_count = response.total_tokens
        self.logger.info(f"Estimated token count: {token_count}")
        return token_count, 0

    def _parse_and_validate_response(self, response: genai.types.GenerateContentResponse) -> PydanticModel:
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
                self.logger.error(f"Gemini API blocked the prompt. Reason: {block_reason}")
                raise ValueError(f"AI model blocked the response due to: {block_reason}")

            self.logger.error(f"Gemini API returned no candidates. Full response: {response}")
            raise ValueError("AI model returned an empty response.")

        try:
            function_call = response.candidates[0].content.parts[0].function_call
            if function_call and function_call.args:
                self.logger.info("Successfully found structured data in function_call.")
                return self.output_schema.model_validate(function_call.args)

            self.logger.warning("No direct function_call found, attempting to parse from text response.")
            text_content = response.text
            self.logger.debug(f"Received text response from Gemini: {text_content}")
            if text_content.strip().startswith("```json"):
                text_content = text_content.strip()[7:-3]

            json_data = json.loads(text_content)
            self.logger.info("Successfully parsed JSON data from text response.")
            return self.output_schema.model_validate(json_data)

        except (
            AttributeError,
            IndexError,
            json.JSONDecodeError,
            ValidationError,
        ) as e:
            self.logger.error(f"Failed to parse or validate the AI's response: {e}")
            self.logger.error(f"Full API Response: {response}")
            raise ValueError(
                "AI model returned a response that could not be parsed into the " "expected structure."
            ) from e

    def _upload_file_to_gemini(self, content: bytes, display_name: str) -> File:
        """Uploads file content to the Gemini File API and waits for it to
        become active.

        This method handles the conversion of in-memory byte content to a
        file-like object, uploads it, and then polls the API until the file's
        status is 'ACTIVE', ensuring it is ready for use in a generation
        request.

        Args:
            content: The raw byte content of the file to be uploaded.
            display_name: The name to assign to the file in the API, which
                          helps in identifying the artifact.

        Returns:
            The file object representing the uploaded and successfully
            processed file.

        Raises:
            Exception: If the file fails to become active after the upload
                       or if any other API error occurs.
        """
        self.logger.info(f"Uploading file '{display_name}' to Gemini File API...")
        try:
            file_stream = io.BytesIO(content)

            mime_type = guess_type(display_name)[0]

            uploaded_file = genai.upload_file(path=file_stream, display_name=display_name, mime_type=mime_type)
            self.logger.info(f"File uploaded successfully: {uploaded_file.name}")

            # Actively wait for the file to be processed by the API.
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = genai.get_file(uploaded_file.name)
                self.logger.debug(f"File status: {uploaded_file.state.name}")

            if uploaded_file.state.name != "ACTIVE":
                raise Exception(
                    f"File '{uploaded_file.name}' failed processing. " f"Final state: {uploaded_file.state.name}"
                )
            return uploaded_file
        except Exception as e:
            self.logger.error(f"Failed to upload or process file for Gemini API: {e}")
            raise
