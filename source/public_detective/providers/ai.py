"""This module provides a generic interface to interact with a Google's AI.

It defines a generic `AiProvider` class that can be specialized with a
Pydantic model to handle structured data output from the AI. The provider
manages API configuration, file uploads, prompt execution, and robust parsing
of the AI's response.
"""

import json
from mimetypes import guess_type
from typing import Generic, TypeVar

import json5
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
    no_ai_tools: bool
    thinking_level: types.ThinkingLevel

    def __init__(
        self,
        output_schema: type[PydanticModel],
        no_ai_tools: bool = False,
    ):
        """Initialize the AiProvider.

        This method configures the Gemini client for a specific output schema.

        Args:
            output_schema: The Pydantic model class that this provider instance
                           will use for all structured outputs.
            no_ai_tools: If True, the AI model will not use any tools.
        """
        self.logger = LoggingProvider().get_logger()
        self.config = ConfigProvider.get_config()
        self.output_schema = output_schema
        self.gcs_provider = GcsProvider()
        self.no_ai_tools = no_ai_tools

        if self.config.GCP_GEMINI_THINKING_LEVEL.upper() == "LOW":
            self.thinking_level = types.ThinkingLevel.LOW
        else:
            self.thinking_level = types.ThinkingLevel.HIGH

        self.client = genai.Client(
            vertexai=True,
            project=self.config.GCP_PROJECT,
            location=self.config.GCP_LOCATION,
            http_options={"base_url": "https://aiplatform.googleapis.com", "api_version": "v1beta1"},
        )

        self.logger.info(
            "Google Generative AI client configured successfully for schema "
            f"'{self.output_schema.__name__}' using Vertex AI backend."
        )

    def get_structured_analysis(
        self, prompt: str, file_uris: list[str], max_output_tokens: int | None = None
    ) -> tuple[PydanticModel, int, int, int, dict, str | None]:
        """Send files for analysis and parse the response.

        This method is designed to be highly robust. It includes a retry mechanism
        that, in case of a specific failure (e.g., the model returning a tool
        call instead of JSON), will make a second attempt with AI tools disabled.
        It also handles cases where the AI response might be empty, blocked by
        safety settings, or returned in a malformed/unexpected structure.

        Args:
            prompt: The instructional prompt for the AI model.
            file_uris: A list of GCS URIs (e.g., gs://bucket/object) for the
                files to be included in the analysis.
            max_output_tokens: An optional integer to set the token limit.
                If `None`, no limit is applied.

        Returns:
            A tuple containing:
            - An instance of the Pydantic model associated with this provider,
              populated with the AI's response.
            - The number of input tokens used.
            - The number of output tokens used.
            - The number of thinking tokens used.
            - A dict containing grounding metadata (search_queries, sources).
            - The raw thoughts from the AI (if available).
        """
        file_parts: list[types.Part] = []
        for gcs_uri in file_uris:
            mime_type = guess_type(gcs_uri)[0] or "application/octet-stream"
            file_parts.append(types.Part.from_uri(file_uri=gcs_uri, mime_type=mime_type))

        all_parts = [types.Part(text=prompt), *file_parts]
        request_contents = types.Content(role="user", parts=all_parts)

        total_input_tokens = 0
        total_output_tokens = 0
        total_thinking_tokens = 0
        grounding_sources: list[dict] = []
        search_queries: list[str] = []

        enable_tools = not self.no_ai_tools
        response = self._generate_content_response(request_contents, max_output_tokens, enable_tools=enable_tools)
        self.logger.info(f"Full API Response (first attempt): {response}")

        if response.usage_metadata:
            total_input_tokens += response.usage_metadata.prompt_token_count or 0
            total_output_tokens += response.usage_metadata.candidates_token_count or 0
            total_thinking_tokens += response.usage_metadata.thoughts_token_count or 0

        validated_response = self._parse_and_validate_response(response)
        self.logger.debug(f"Validated AI response: {validated_response}")

        if response.candidates:
            for index, candidate in enumerate(response.candidates):
                metadata = getattr(candidate, "grounding_metadata", None)
                if metadata is None:
                    continue

                chunks = getattr(metadata, "grounding_chunks", [])
                if chunks:
                    for chunk in chunks:
                        web = getattr(chunk, "web", None)
                        if web:
                            uri = getattr(web, "uri", None)
                            title = getattr(web, "title", None)
                            if uri:
                                grounding_sources.append({"original_url": uri, "title": title})

                queries = getattr(metadata, "web_search_queries", [])
                if queries:
                    search_queries.extend(queries)

                self.logger.info(
                    "Grounding metadata web_search_queries (candidate %s): %s",
                    index,
                    queries,
                )
        self.logger.debug("Successfully received response from Generative AI API.")

        unique_sources = {s["original_url"]: s for s in grounding_sources}.values()
        unique_queries = list(set(search_queries))

        grounding_metadata = {
            "search_queries": unique_queries,
            "sources": list(unique_sources),
        }

        thoughts = []
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if getattr(part, "thought", False) and part.text:
                    thoughts.append(part.text)

        full_thoughts = "\n\n".join(thoughts) if thoughts else None

        return (
            validated_response,
            total_input_tokens,
            total_output_tokens,
            total_thinking_tokens,
            grounding_metadata,
            full_thoughts,
        )

    def count_tokens_for_analysis(self, prompt: str, file_uris: list[str]) -> tuple[int, int, int]:
        """Calculate the number of tokens for a given prompt and files.

        Args:
            prompt: The instructional prompt for the AI model.
            file_uris: A list of GCS URIs (e.g., gs://bucket/object) for the
                files to be included in the analysis.

        Returns:
            A tuple containing the total number of input tokens, 0 for output
            tokens, and 0 for thinking tokens.
        """
        file_parts: list[types.Part] = []
        for gcs_uri in file_uris:
            mime_type = guess_type(gcs_uri)[0]
            if not mime_type:
                mime_type = "application/octet-stream"
            file_parts.append(types.Part.from_uri(file_uri=gcs_uri, mime_type=mime_type))

        all_parts = [types.Part(text=prompt), *file_parts]
        request_contents = types.Content(role="user", parts=all_parts)
        response = self.client.models.count_tokens(model=self.config.GCP_GEMINI_MODEL, contents=request_contents)
        token_count = response.total_tokens
        self.logger.info(f"Estimated token count: {token_count}")
        return token_count or 0, 0, 0

    def _parse_and_validate_response(self, response) -> PydanticModel:  # type: ignore
        """Parse the AI's response, handling multiple potential formats and errors.

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
            self.logger.info(f"Raw text response from Generative AI before parsing: {response_text}")

            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]

            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]

            cleaned_text = cleaned_text.strip()

            json_data = json5.loads(cleaned_text)
            self.logger.info("Successfully parsed JSON data from text response.")
            return self.output_schema.model_validate(json_data)

        except (json.JSONDecodeError, ValueError, ValidationError) as e:
            self.logger.error(f"Failed to parse or validate the AI's response: {e}")
            self.logger.error(f"Full API Response: {response}")

            raise ValueError(
                f"AI model returned a response that could not be parsed into the expected structure: {e}"
            ) from e

    def _generate_content_response(
        self, request_contents: types.Content, max_output_tokens: int | None, enable_tools: bool
    ) -> types.GenerateContentResponse:
        """Generate model output using the configured schema.

        Args:
            request_contents: The structured prompt and attachments sent to Gemini.
            max_output_tokens: Optional limit for the model output.
            enable_tools: Flag indicating whether external tools should be enabled.

        Returns:
            The raw GenerateContent response from the Gemini API.
        """
        tools: list[types.Tool] = []
        tool_config: types.ToolConfig | None = None

        if enable_tools:
            tools.append(types.Tool(google_search=types.GoogleSearch()))
            tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.AUTO)
            )

        return self.client.models.generate_content(
            model=self.config.GCP_GEMINI_MODEL,
            contents=request_contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=self.output_schema,
                max_output_tokens=max_output_tokens,
                tools=tools,
                tool_config=tool_config,
                thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level, include_thoughts=True),
            ),
        )

    def _should_retry_without_tools(self, response) -> bool:  # type: ignore
        """Determine whether the response suggests retrying without tools.

        Args:
            response: The initial GenerateContent response to inspect.

        Returns:
            True when the response unexpectedly includes a raw tool call.
        """
        if not response.candidates:
            return False

        first_candidate = response.candidates[0]
        candidate_content = getattr(first_candidate, "content", None)
        if candidate_content is None:
            return False

        parts = getattr(candidate_content, "parts", None)
        if parts is None:
            return False

        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                self.logger.debug(f"Checking part text for tool call: '{text}'")
                if "call:google_search.search" in text:
                    return True
        return False
