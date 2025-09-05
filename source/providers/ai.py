"""This module provides a generic interface to interact with a Google's AI.

It defines a generic `AiProvider` class that can be specialized with a
Pydantic model to handle structured data output from the AI. The provider
manages API configuration, file uploads, prompt execution, and robust parsing
of the AI's response.
"""

from mimetypes import guess_type
from typing import Any, Generic, TypeVar

import vertexai
from providers.config import Config, ConfigProvider
from providers.logging import Logger, LoggingProvider
from pydantic import BaseModel, ValidationError
from vertexai.generative_models import (
    FunctionDeclaration,
    GenerationConfig,
    GenerationResponse,
    GenerativeModel,
    Part,
    Tool,
)


def _clean_schema_for_vertex_ai(schema: dict) -> dict:
    """
    Recursively cleans a Pydantic JSON schema to make it compatible with
    Vertex AI's function calling, which does not support 'anyOf' with 'null' type.
    """
    if isinstance(schema, dict):
        # Remove 'anyOf' with 'null' for optional fields
        if "anyOf" in schema:
            schema["anyOf"] = [s for s in schema["anyOf"] if s.get("type") != "null"]
            if len(schema["anyOf"]) == 1:
                return _clean_schema_for_vertex_ai(schema["anyOf"][0])

        # Recurse into nested schemas
        for key, value in schema.items():
            schema[key] = _clean_schema_for_vertex_ai(value)

    elif isinstance(schema, list):
        return [_clean_schema_for_vertex_ai(item) for item in schema]

    return schema


PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class AiProvider(Generic[PydanticModel]):
    """
    Provides a generic interface to interact with the Google Vertex AI model,
    specialized for a specific Pydantic output model.
    """

    logger: Logger
    config: Config
    model: GenerativeModel
    output_schema: type[PydanticModel]

    def __init__(self, output_schema: type[PydanticModel]):
        """
        Initializes the AiProvider, configuring the Vertex AI client for a specific
        output schema.

        Args:
            output_schema: The Pydantic model class that this provider instance
                           will use for all structured outputs.
        """
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.output_schema = output_schema

        if not self.config.GCP_PROJECT:
            raise ValueError("GCP_PROJECT must be configured to use the AI provider.")

        vertexai.init(project=self.config.GCP_PROJECT)
        self.model = GenerativeModel(self.config.GCP_GEMINI_MODEL)
        self.logger.info(
            "Google Vertex AI client configured successfully for schema " f"'{self.output_schema.__name__}'."
        )

    def get_structured_analysis(
        self, prompt: str, files: list[tuple[str, bytes]], max_output_tokens: int | None = None
    ) -> tuple[PydanticModel, int, int]:
        """
        Sends a prompt with files for analysis and parses the structured response
        into the Pydantic model instance defined for this provider.

        Args:
            prompt: The instructional prompt for the AI model.
            files: A list of tuples, where each tuple contains the file path and its byte content.
            max_output_tokens: An optional integer to set the token limit.

        Returns:
            A tuple containing the Pydantic model instance, input tokens, and output tokens.
        """
        self.logger.info(f"Sending request to Vertex AI for {len(files)} files.")
        parts: list[Any] = [prompt]
        for file_path, file_content in files:
            mime_type = guess_type(file_path)[0] or "application/octet-stream"
            parts.append(Part.from_data(data=file_content, mime_type=mime_type))

        # Count input tokens before making the call
        input_tokens = self.model.count_tokens(parts).total_tokens

        cleaned_schema = _clean_schema_for_vertex_ai(self.output_schema.model_json_schema())
        tool = Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="structured_analysis_output",
                    description="Outputs the structured analysis of the procurement documents.",
                    parameters=cleaned_schema,
                )
            ]
        )
        response = self._generate_content_with_structured_output(parts, tool, max_output_tokens)
        validated_response = self._parse_and_validate_response(response)

        # Count output tokens after getting the response
        output_tokens = self.model.count_tokens([response.candidates[0].content]).total_tokens

        return validated_response, input_tokens, output_tokens

    def count_tokens_for_analysis(self, prompt: str, files: list[tuple[str, bytes]]) -> tuple[int, int]:
        """
        Calculates the number of tokens for a given prompt and list of files.
        """
        self.logger.info("Counting tokens for analysis...")
        parts: list[Any] = [prompt]
        for file_path, file_content in files:
            mime_type = guess_type(file_path)[0] or "application/octet-stream"
            parts.append(Part.from_data(data=file_content, mime_type=mime_type))

        token_count = self.model.count_tokens(parts).total_tokens
        self.logger.info(f"Estimated token count: {token_count}")
        return token_count, 0

    def _generate_content_with_structured_output(
        self, parts: list, tool: Tool, max_output_tokens: int | None
    ) -> GenerationResponse:
        """Generates content with a structured output.

        Args:
            parts: The parts of the content to generate.
            tool: The tool to use for generation.
            max_output_tokens: The maximum number of output tokens.

        Returns:
            The generation response.
        """
        self.logger.info("Sending request to Vertex AI API with function calling.")
        generation_config = GenerationConfig(max_output_tokens=max_output_tokens) if max_output_tokens else None

        response = self.model.generate_content(
            parts,
            tools=[tool],
            generation_config=generation_config,
        )
        self.logger.debug(f"Successfully received response from Vertex AI API: {response}")
        return response

    def _parse_and_validate_response(self, response: GenerationResponse) -> PydanticModel:
        """
        Parses the AI's response, expecting a function call with the structured data.

        Args:
            response: The response from the AI model.

        Returns:
            The parsed and validated Pydantic model.
        """
        try:
            function_call = response.candidates[0].content.parts[0].function_call
            if not function_call or not function_call.args:
                raise ValueError("Model did not return a function call with arguments.")

            self.logger.info("Successfully found structured data in function_call.")
            return self.output_schema.model_validate(function_call.args)

        except (AttributeError, IndexError, ValidationError) as e:
            self.logger.error(f"Failed to parse or validate the AI's response: {e}")
            self.logger.error(f"Full API Response: {response}")
            raise ValueError("AI model returned a response that could not be parsed.") from e
