"""Thin wrapper around the Google Gemini API plus a retry helper."""

import json
from typing import Callable, TypeVar

T = TypeVar("T")

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_MS = 60_000


class RetriesExhausted(Exception):
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"{attempts} attempts failed: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


def call_with_retries(operation: Callable[[], T], max_attempts: int = MAX_ATTEMPTS) -> tuple[T, int]:
    """Run `operation` until it succeeds. Returns (result, attempts used).

    Any exception (request error, invalid JSON, failed validation) triggers a retry
    (N-10); raises RetriesExhausted after `max_attempts` failures.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation(), attempt
        except Exception as exc:  # noqa: BLE001 - any failure triggers a retry
            last_error = exc
    raise RetriesExhausted(max_attempts, last_error)


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout_ms: int = REQUEST_TIMEOUT_MS):
        self._api_key = api_key
        self._model = model
        self._timeout_ms = timeout_ms

    def generate_json(self, contents: list | str):
        """Call Gemini in JSON mode and return the parsed JSON document."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key, http_options=types.HttpOptions(timeout=self._timeout_ms))
        response = client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)

    @staticmethod
    def pdf_part(pdf_content: bytes):
        from google.genai import types

        return types.Part.from_bytes(data=pdf_content, mime_type="application/pdf")
