"""AI adapters without network: retry policy, response validation and agents behind a stub client."""

import base64
import io
import json
from contextlib import nullcontext
from datetime import time
from urllib.error import HTTPError

import pytest

from app.application.errors import AnalysisFailed, RecognitionFailed
from app.domain.entities import StudyEvent, StudyEventType, WorkShift
from app.domain.weekday import Weekday
from app.infrastructure.ai.gemini_client import RetriesExhausted, call_with_retries
from app.infrastructure.ai import claude_client
from app.infrastructure.ai.claude_client import AnthropicApiError, ClaudeClient
from app.infrastructure.ai.gemini_conflict_analyzer import GeminiConflictAnalyzer, parse_conflicts
from app.infrastructure.ai.gemini_schedule_recognizer import GeminiScheduleRecognizer, parse_events
from app.infrastructure.config import Settings

GOOD_ENTRY = {
    "subject": "Programavimas", "event_type": "PASKAITA", "day_of_week": "PIRMADIENIS",
    "start_time": "09:00", "end_time": "10:30", "room": "A1", "is_mandatory": True,
}


class StubClient:
    """Stands in for GeminiClient: returns queued responses, raising any Exception instance."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def generate_json(self, contents):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @staticmethod
    def pdf_part(pdf_content):
        return pdf_content


def test_retry_succeeds_on_the_third_attempt():
    outcomes = iter([RuntimeError("503"), RuntimeError("503"), "ok"])

    def operation():
        value = next(outcomes)
        if isinstance(value, Exception):
            raise value
        return value

    delays = []
    assert call_with_retries(operation, sleep=delays.append) == ("ok", 3)
    assert len(delays) == 2 and delays[0] >= 1 and delays[1] >= 2


def test_retry_gives_up_after_three_attempts():
    calls = []

    def operation():
        calls.append(1)
        raise RuntimeError("always failing")

    with pytest.raises(RetriesExhausted) as exc:
        call_with_retries(operation, sleep=lambda _: None)
    assert len(calls) == 3 and exc.value.attempts == 3


def test_retry_uses_retry_after_header():
    class RateLimitedError(Exception):
        retry_after_seconds = "4"

    delays = []
    outcomes = iter([RateLimitedError("429"), "ok"])

    def operation():
        value = next(outcomes)
        if isinstance(value, Exception):
            raise value
        return value

    assert call_with_retries(operation, sleep=delays.append) == ("ok", 2)
    assert len(delays) == 1 and delays[0] >= 4


def test_claude_client_posts_json_and_pdf_without_network(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        body = json.dumps({"content": [{"type": "text", "text": '[{"ok": true}]'}]}).encode()
        return nullcontext(io.BytesIO(body))

    monkeypatch.setattr(claude_client, "urlopen", fake_urlopen)
    client = ClaudeClient("test-api-key", "claude-test")

    assert client.generate_json([client.pdf_part(b"pdf-bytes"), "Return JSON"]) == [{"ok": True}]

    request = captured["request"]
    payload = json.loads(request.data)
    assert request.full_url == "https://api.anthropic.com/v1/messages"
    assert request.get_header("X-api-key") == "test-api-key"
    assert request.get_header("Anthropic-version") == "2023-06-01"
    assert captured["timeout"] == 60
    assert payload["model"] == "claude-test"
    assert payload["messages"][0]["content"][0]["source"]["data"] == base64.b64encode(b"pdf-bytes").decode()
    assert payload["messages"][0]["content"][1]["text"] == "Return JSON"


def test_claude_rate_limit_error_exposes_retry_after(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            429,
            "rate limited",
            {"Retry-After": "3"},
            io.BytesIO(b'{"error":{"message":"too many requests"}}'),
        )

    monkeypatch.setattr(claude_client, "urlopen", fake_urlopen)
    with pytest.raises(AnthropicApiError) as exc:
        ClaudeClient("test-api-key", "claude-test").generate_json("hello")
    assert exc.value.status == 429
    assert exc.value.retry_after_seconds == "3"


def test_settings_select_claude_from_environment(monkeypatch, tmp_path):
    for key, value in {
        "DB_NAME": "test",
        "DB_USER": "test",
        "DB_PASSWORD": "test",
        "SECRET_KEY": "test-secret",
        "AI_PROVIDER": "CLAUDE",
        "CLAUDE_MODEL": "claude-test-model",
    }.items():
        monkeypatch.setenv(key, value)

    settings = Settings(path=str(tmp_path / "missing.ini"))

    assert settings.ai_provider == "claude"
    assert settings.claude_model == "claude-test-model"


@pytest.mark.parametrize(
    "broken",
    [
        {},  # not a list
        [],  # empty list
        ["text"],  # entry is not an object
        [{**GOOD_ENTRY, "subject": ""}],
        [{**GOOD_ENTRY, "event_type": "EGZAMINAS"}],
        [{**GOOD_ENTRY, "day_of_week": "MONDAY"}],
        [{**GOOD_ENTRY, "start_time": "9am"}],
        [{**GOOD_ENTRY, "start_time": "11:00", "end_time": "10:00"}],
    ],
)
def test_recognizer_response_with_wrong_structure_is_rejected(broken):
    with pytest.raises(ValueError):
        parse_events(broken)


def test_recognizer_parses_valid_entries():
    [event] = parse_events([GOOD_ENTRY])
    assert event.subject_name == "Programavimas" and event.event_type == StudyEventType.LECTURE
    assert event.weekday == Weekday.MONDAY and event.start_time == time(9, 0) and event.room == "A1"


def test_recognizer_retries_then_returns_events():
    client = StubClient(RuntimeError("503"), {"not": "a list"}, [GOOD_ENTRY])
    result = GeminiScheduleRecognizer(client).recognize(b"%PDF")
    assert result.attempts == 3 and client.calls == 3 and len(result.events) == 1


def test_recognizer_fails_after_three_invalid_responses():
    client = StubClient(RuntimeError("x"), [], ["bad"])
    with pytest.raises(RecognitionFailed) as exc:
        GeminiScheduleRecognizer(client).recognize(b"%PDF")
    assert exc.value.attempts == 3 and client.calls == 3


def test_analyzer_rejects_unknown_ids_and_non_integers():
    with pytest.raises(ValueError):
        parse_conflicts([{"study_event_id": 9, "work_shift_id": 1, "overlap_minutes": 5}], {1}, {1})
    with pytest.raises(ValueError):
        parse_conflicts([{"study_event_id": "1", "work_shift_id": 1, "overlap_minutes": 5}], {1}, {1})
    assert parse_conflicts([], {1}, {1}) == []


def test_analyzer_skips_the_ai_call_when_there_is_nothing_to_compare():
    client = StubClient()
    result = GeminiConflictAnalyzer(client).analyze([], [])
    assert result.conflicts == [] and client.calls == 0


def test_analyzer_returns_detected_conflicts_and_reports_failure():
    event = StudyEvent(1, "Programavimas", StudyEventType.LECTURE, Weekday.MONDAY, time(9, 0), time(10, 30), None)
    shift = WorkShift(1, "Kavine", Weekday.MONDAY, time(10, 0), time(14, 0))
    detected = [{"study_event_id": 1, "work_shift_id": 1, "overlap_minutes": 30}]

    ok = GeminiConflictAnalyzer(StubClient(detected)).analyze([event], [shift])
    assert (ok.conflicts[0].overlap_minutes, ok.attempts) == (30, 1)

    failing = StubClient(RuntimeError("1"), RuntimeError("2"), RuntimeError("3"))
    with pytest.raises(AnalysisFailed):
        GeminiConflictAnalyzer(failing).analyze([event], [shift])
