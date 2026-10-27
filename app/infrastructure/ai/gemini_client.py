"""Gemini API wrapper and shared retry helper for AI providers."""

import email.utils
import json
import random
import time
from datetime import datetime, timezone
from typing import Callable, Protocol, TypeVar

T = TypeVar("T")


class JsonClient(Protocol):
    def generate_json(self, contents: list | str): ...

    @staticmethod
    def pdf_part(pdf_content: bytes): ...

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_MS = 60_000
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0


class RetriesExhausted(Exception):
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"{attempts} attempts failed: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


def call_with_retries(
    operation: Callable[[], T],
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, int]:
    """Run `operation` until it succeeds. Returns (result, attempts used).

    Any exception (request error, invalid JSON, failed validation) triggers an
    exponential backoff retry (N-10). A provider Retry-After value takes precedence.
    Raises RetriesExhausted after `max_attempts` failures.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation(), attempt
        except Exception as exc:  # noqa: BLE001 - any failure triggers a retry
            last_error = exc
            if attempt < max_attempts:
                delay = min(INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
                retry_after = _retry_after_seconds(exc)
                if retry_after is not None:
                    delay = max(delay, retry_after)
                # Small jitter prevents simultaneous clients from retrying together.
                sleep(delay + random.uniform(0, min(delay * 0.1, 1.0)))
    raise RetriesExhausted(max_attempts, last_error)


def _retry_after_seconds(error: Exception) -> float | None:
    value = getattr(error, "retry_after_seconds", None)
    if value is None:
        headers = getattr(error, "headers", None)
        if headers is None:
            headers = getattr(getattr(error, "response", None), "headers", None)
        if headers is not None:
            value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = email.utils.parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


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
