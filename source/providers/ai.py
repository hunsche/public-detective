import io
import json
import time
from typing import Generic, Type, TypeVar

import google.generativeai as genai
from google.ai.generativelanguage import File
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

        genai.configure(api_key=self.config.GCP_GEMINI_API_KEY)
        self.model = genai.GenerativeModel(self.config.GCP_GEMINI_MODEL)
        self.logger.info(
            f"Google Gemini client configured successfully for schema '{self.output_schema.__name__}'."
        )

    def get_structured_analysis(
        self,
        prompt: str,
        file_content: bytes,
        file_display_name: str,
    ) -> PydanticModel:
        """
        Uploads a file, sends it with a prompt for analysis, and parses the
        structured response into the Pydantic model instance defined for this provider.

        This method is designed to be highly robust, handling cases where the AI
        response might be empty, blocked by safety settings, or returned in
        an unexpected format.

        Args:
            prompt: The instructional prompt for the AI model.
            file_content: The raw byte content of the file to be analyzed.
            file_display_name: A descriptive name for the uploaded file.

        Returns:
            An instance of the Pydantic model associated with this provider,
            populated with the AI's response.

        Raises:
            ValueError: If the AI model returns a blocked, empty, or
                        unparsable response.
        """
        # uploaded_file = self._upload_file_to_gemini(file_content, file_display_name)

        with open("/tmp/procurement_files/teste/edital_1.zip", "rb") as arquivo:
            content = arquivo.read()
            uploaded_file = self._upload_file_to_gemini(content, "edital_1.zip")

        try:
            self.logger.info(f"Sending request to Gemini API for '{file_display_name}'.")

            response = self.model.generate_content(
                [prompt, uploaded_file],
                generation_config=genai.types.GenerationConfig(
                    response_schema=self.output_schema,
                    response_mime_type="application/json",
                ),
            )
            self.logger.debug("Successfully received response from Gemini API.")

            return self._parse_and_validate_response(response)

        finally:
            self.logger.info(f"Deleting uploaded file: {uploaded_file.name}")
            genai.delete_file(uploaded_file.name)

    def _parse_and_validate_response(
        self, response: genai.types.GenerateContentResponse
    ) -> PydanticModel:
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
                self.logger.error(
                    f"Gemini API blocked the prompt. Reason: {block_reason}"
                )
                raise ValueError(f"AI model blocked the response due to: {block_reason}")

            self.logger.error(
                f"Gemini API returned no candidates. Full response: {response}"
            )
            raise ValueError("AI model returned an empty response.")

        try:
            if response.candidates[0].content.parts[0].function_call.args:
                self.logger.info("Successfully found structured data in function_call.")
                return self.output_schema.model_validate(
                    response.candidates[0].content.parts[0].function_call.args
                )

            self.logger.warning(
                "No direct function_call found, attempting to parse from text response."
            )
            text_content = response.text
            if text_content.strip().startswith("```json"):
                text_content = text_content.strip()[7:-3]

            json_data = json.loads(text_content)
            self.logger.info("Successfully parsed JSON data from text response.")
            return self.output_schema.model_validate(json_data)

        except (AttributeError, IndexError, json.JSONDecodeError, ValidationError) as e:
            self.logger.error(f"Failed to parse or validate the AI's response: {e}")
            self.logger.error(f"Full API Response: {response}")
            raise ValueError(
                "AI model returned a response that could not be parsed into the expected structure."
            ) from e

    def _upload_file_to_gemini(self, content: bytes, display_name: str) -> File:
        """Uploads file content to the Gemini File API and waits for it to
        become active.

        Args:
            content: The raw byte content of the file.
            display_name: The name to assign to the file in the API.

        Returns:
            The file object representing the uploaded and processed file.
        """
        self.logger.info(f"Uploading file '{display_name}' to Gemini File API...")
        try:
            file_stream = io.BytesIO(content)
            uploaded_file = genai.upload_file(
                path="/tmp/procurement_files/teste/edital_1.zip",
                # display_name=display_name,
                # mime_type=(
                #     "application/pdf"
                #     if display_name.lower().endswith(".pdf")
                #     else "application/zip"
                # ),
            )
            self.logger.info(f"File uploaded successfully: {uploaded_file.name}")

            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = genai.get_file(uploaded_file.name)
                self.logger.debug(f"File status: {uploaded_file.state.name}")

            if uploaded_file.state.name != "ACTIVE":
                raise Exception(
                    f"File '{uploaded_file.name}' failed processing. "
                    f"State: {uploaded_file.state.name}"
                )
            return uploaded_file
        except Exception as e:
            self.logger.error(f"Failed to upload or process file for Gemini API: {e}")
            raise
