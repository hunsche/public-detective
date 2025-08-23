import io
import json
import time
from mimetypes import guess_type
from typing import Generic, List, Tuple, Type, TypeVar

import google.generativeai as genai
from google.ai.generativelanguage import File
from pydantic import BaseModel, ValidationError
from providers.config import Config, ConfigProvider
from providers.converter import ConverterProvider
from providers.logging import Logger, LoggingProvider

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class AiProvider(Generic[PydanticModel]):
    """
    Provides a generic interface to interact with the Google Gemini AI model,
    handling file conversions and structured data parsing.
    """

    def __init__(self, output_schema: type[PydanticModel]):
        """
        Initializes the AiProvider, configuring the Gemini client and the
        file converter.
        """
        self.logger: Logger = LoggingProvider.get_logger()
        self.config: Config = ConfigProvider.get_config()
        self.output_schema: type[PydanticModel] = output_schema
        self.converter: ConverterProvider | None = None

        try:
            self.converter = ConverterProvider()
        except RuntimeError:
            self.logger.warning("File converter is not available.")

        genai.configure(api_key=self.config.GCP_GEMINI_API_KEY)
        self.model = genai.GenerativeModel(self.config.GCP_GEMINI_MODEL)
        self.logger.info(f"AI Provider configured for schema '{self.output_schema.__name__}'.")

    def convert_files(self, files: List[Tuple[str, bytes]]) -> List[Tuple[str, bytes]]:
        """
        Converts a list of files to AI-ingestible formats (PDF, CSV).

        Returns a new list of tuples with the converted file contents and new names.
        Skips conversion for files that don't need it or if the converter is unavailable.
        """
        if not self.converter:
            self.logger.warning("Converter not available. Skipping all file conversions.")
            return files

        processed_files = []
        for display_name, content in files:
            file_extension = display_name.lower().rsplit(".", 1)[-1]
            target_format = None

            if file_extension in ["docx", "doc", "rtf"]:
                target_format = "pdf"
            elif file_extension in ["xlsx", "xls"]:
                target_format = "csv"

            if target_format:
                self.logger.info(f"Converting '{display_name}' to {target_format.upper()}.")
                try:
                    converted_content = self.converter.convert_file(
                        content, display_name, target_format
                    )
                    new_name = f"{display_name}.{target_format}"
                    processed_files.append((new_name, converted_content))
                except Exception as e:
                    self.logger.error(f"Failed to convert '{display_name}': {e}")
                    processed_files.append((display_name, content)) # Append original on failure
            else:
                processed_files.append((display_name, content))

        return processed_files

    def get_structured_analysis(
        self, prompt: str, files: List[Tuple[str, bytes]]
    ) -> PydanticModel:
        """
        Uploads files, sends a prompt for analysis, and parses the structured response.
        """
        uploaded_files = []
        try:
            for display_name, content in files:
                uploaded_files.append(self._upload_file_to_gemini(content, display_name))

            contents = [prompt] + uploaded_files
            response = self.model.generate_content(
                contents,
                generation_config=genai.types.GenerationConfig(
                    response_schema=self.output_schema,
                    response_mime_type="application/json",
                ),
            )
            self.logger.debug("Successfully received response from Gemini API.")
            return self._parse_and_validate_response(response)
        finally:
            for uploaded_file in uploaded_files:
                self.logger.info(f"Deleting uploaded file: {uploaded_file.name}")
                genai.delete_file(uploaded_file.name)

    def _parse_and_validate_response(
        self, response: genai.types.GenerateContentResponse
    ) -> PydanticModel:
        """Parses and validates the AI's JSON response into a Pydantic model."""
        if not response.candidates:
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason = response.prompt_feedback.block_reason.name
                raise ValueError(f"AI model blocked the response due to: {block_reason}")
            raise ValueError("AI model returned an empty response.")

        try:
            if response.candidates[0].content.parts[0].function_call.args:
                return self.output_schema.model_validate(
                    response.candidates[0].content.parts[0].function_call.args
                )

            text_content = response.text
            if text_content.strip().startswith("```json"):
                text_content = text_content.strip()[7:-3]
            json_data = json.loads(text_content)
            return self.output_schema.model_validate(json_data)
        except (AttributeError, IndexError, json.JSONDecodeError, ValidationError) as e:
            self.logger.error(f"Failed to parse or validate AI response: {e}\nFull response: {response}")
            raise ValueError("AI model returned an unparsable response.") from e

    def _upload_file_to_gemini(self, content: bytes, display_name: str) -> File:
        """Uploads a single file to the Gemini File API and waits for it to become active."""
        self.logger.info(f"Uploading file '{display_name}' to Gemini File API...")
        try:
            file_stream = io.BytesIO(content)
            mime_type = guess_type(display_name)[0] or "application/octet-stream"
            uploaded_file = genai.upload_file(
                path=file_stream, display_name=display_name, mime_type=mime_type
            )
            self.logger.info(f"File '{uploaded_file.name}' uploaded successfully. Waiting for processing...")

            while uploaded_file.state.name == "PROCESSING":
                time.sleep(2)
                uploaded_file = genai.get_file(uploaded_file.name)

            if uploaded_file.state.name != "ACTIVE":
                raise Exception(f"File processing failed. Final state: {uploaded_file.state.name}")

            self.logger.info(f"File '{uploaded_file.name}' is now active.")
            return uploaded_file
        except Exception as e:
            self.logger.error(f"Failed to upload or process file '{display_name}' for Gemini API: {e}", exc_info=True)
            raise
