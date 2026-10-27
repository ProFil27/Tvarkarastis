"""Analysis agent (AI agent 2): finds overlaps between study events and work shifts (F-13, AN-1..AN-3)."""

import json

from app.application.errors import AnalysisFailed
from app.application.ports import AnalysisResult
from app.application.validation import format_time
from app.domain.entities import DetectedConflict, StudyEvent, WorkShift
from app.infrastructure.ai.gemini_client import JsonClient, RetriesExhausted, call_with_retries

_PROMPT = """You receive lists of study events and work shifts (JSON). Find every pair
(study event, work shift) on the same weekday whose time intervals overlap.
If one interval ends exactly when the other starts, it is NOT a conflict.
Return ONLY a JSON array (no extra text) whose elements are:
  {"study_event_id": <int>, "work_shift_id": <int>, "overlap_minutes": <int>}
If there are no conflicts, return [].

Data:
"""


class ConflictAnalyzer:
    def __init__(self, client: JsonClient):
        self._client = client

    def analyze(self, events: list[StudyEvent], shifts: list[WorkShift]) -> AnalysisResult:
        if not events or not shifts:
            return AnalysisResult([], 0)

        prompt = _PROMPT + _serialize(events, shifts)
        known_events = {e.id for e in events}
        known_shifts = {s.id for s in shifts}

        def attempt() -> list[DetectedConflict]:
            return parse_conflicts(self._client.generate_json(prompt), known_events, known_shifts)

        try:
            conflicts, attempts = call_with_retries(attempt)
        except RetriesExhausted as exc:
            raise AnalysisFailed(f"Analysis failed after {exc.attempts} attempts: {exc.last_error}", exc.attempts)
        return AnalysisResult(conflicts, attempts)


def _serialize(events: list[StudyEvent], shifts: list[WorkShift]) -> str:
    def interval(item) -> dict:
        return {
            "id": item.id,
            "day_of_week": item.weekday.value,
            "start": format_time(item.start_time),
            "end": format_time(item.end_time),
        }

    return json.dumps(
        {"study_events": [interval(e) for e in events], "work_shifts": [interval(s) for s in shifts]},
        ensure_ascii=False,
    )


def parse_conflicts(data, known_events: set[int], known_shifts: set[int]) -> list[DetectedConflict]:
    """Validate the agent's response structure (F-14); raises ValueError if it is wrong."""
    if not isinstance(data, list):
        raise ValueError("Response must be a JSON array.")

    conflicts = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Every entry must be a JSON object.")
        event_id, shift_id, minutes = item.get("study_event_id"), item.get("work_shift_id"), item.get("overlap_minutes")
        if not all(isinstance(v, int) for v in (event_id, shift_id, minutes)):
            raise ValueError("Entries need integer study_event_id, work_shift_id and overlap_minutes.")
        if event_id not in known_events or shift_id not in known_shifts:
            raise ValueError("Response contains unknown IDs.")
        conflicts.append(DetectedConflict(event_id, shift_id, minutes))
    return conflicts


# Backwards-compatible import name; the adapter is shared by both AI providers.
GeminiConflictAnalyzer = ConflictAnalyzer
