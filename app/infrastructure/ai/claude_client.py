"""Small Anthropic Messages API client using the Python standard library."""

import base64
import json
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.infrastructure.ai.gemini_client import REQUEST_TIMEOUT_MS

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


@dataclass(frozen=True)
class PdfPart:
    data: bytes


class AnthropicApiError(Exception):
    def __init__(self, status: int, message: str, retry_after_seconds: str | None = None):
        super().__init__(f"Anthropic API returned HTTP {status}: {message}")
        self.status = status
        self.retry_after_seconds = retry_after_seconds


class ClaudeClient:
    def __init__(self, api_key: str, model: str, timeout_ms: int = REQUEST_TIMEOUT_MS):
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_ms / 1000

    def generate_json(self, contents: list | str):
        """Send a user message to Claude and parse its text response as JSON."""
        content = contents if isinstance(contents, list) else [contents]
        blocks = []
        for part in content:
            if isinstance(part, PdfPart):
                blocks.append(
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.standard_b64encode(part.data).decode("ascii"),
                        },
                    }
                )
            else:
                blocks.append({"type": "text", "text": str(part)})

        payload = json.dumps(
            {"model": self._model, "max_tokens": 4096, "messages": [{"role": "user", "content": blocks}]}
        ).encode("utf-8")
        request = Request(
            ANTHROPIC_MESSAGES_URL,
            data=payload,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                result = json.loads(response.read())
        except HTTPError as exc:
            try:
                error_body = json.loads(exc.read())
                message = error_body.get("error", {}).get("message", "request failed")
            except (ValueError, AttributeError):
                message = "request failed"
            raise AnthropicApiError(exc.code, message, exc.headers.get("Retry-After")) from exc

        text = "".join(block.get("text", "") for block in result.get("content", []) if block.get("type") == "text")
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)

    @staticmethod
    def pdf_part(pdf_content: bytes) -> PdfPart:
        return PdfPart(pdf_content)
