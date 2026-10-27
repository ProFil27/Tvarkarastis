"""Recognition agent (AI agent 1): timetable PDF -> structured study events (F-04, AA-1..AA-4)."""

from app.application.errors import RecognitionFailed
from app.application.ports import RecognitionResult
from app.application.validation import TIME_FORMAT, parse_time
from app.domain.entities import StudyEvent, StudyEventType
from app.domain.weekday import Weekday
from app.infrastructure.ai.gemini_client import JsonClient, RetriesExhausted, call_with_retries

_PROMPT = """You are analysing a university timetable PDF (Lithuanian). Return ONLY a JSON
array (no extra text) in which every element is one lecture / practical /
laboratory session with exactly these fields:
  "subject": subject name (string)
  "event_type": one of """ + ", ".join(f'"{t.value}"' for t in StudyEventType) + """
  "day_of_week": one of """ + ", ".join(f'"{d.value}"' for d in Weekday) + """
  "start_time": start time as "HH:MM" (24h)
  "end_time": end time as "HH:MM" (24h), later than start_time
  "room": room as written in the timetable (string or null)
  "is_mandatory": true or false

Rules:
  - Map the Lithuanian type: "Paskaitos" -> "PASKAITA", "Pratybos" -> "PRATYBOS",
    "Laboratoriniai darbai" -> "LABORATORINIS_DARBAS".
  - Weekday headings map to the codes above (Pirmadienis -> PIRMADIENIS, ...,
    Trečiadienis -> TRECIADIENIS, Šeštadienis -> SESTADIENIS).
  - Do not include the subject code in parentheses (e.g. "(FMITB24710)") in the name.
  - Keep the room exactly as written (e.g. "S6(SRL-I) 501").
  - If several rows share the same time slot (different weeks or subgroups),
    return every row separately.
  - Ignore everything that is not a timetable entry (maps, logos).

Example: [{"subject": "Programming", "event_type": "PASKAITA",
"day_of_week": "PIRMADIENIS", "start_time": "09:00", "end_time": "10:30",
"room": "SRK-I", "is_mandatory": true}]
"""


class ScheduleRecognizer:
    def __init__(self, client: JsonClient):
        self._client = client

    def recognize(self, pdf_content: bytes) -> RecognitionResult:
        def attempt() -> list[StudyEvent]:
            data = self._client.generate_json([self._client.pdf_part(pdf_content), _PROMPT])
            return parse_events(data)

        try:
            events, attempts = call_with_retries(attempt)
        except RetriesExhausted as exc:
            raise RecognitionFailed(f"Recognition failed after {exc.attempts} attempts: {exc.last_error}", exc.attempts)
        return RecognitionResult(events, attempts)


def parse_events(data) -> list[StudyEvent]:
    """Validate the agent's response structure (AA-4); raises ValueError if it is wrong."""
    if not isinstance(data, list) or not data:
        raise ValueError("Response is not a non-empty JSON array.")

    events = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("Every entry must be a JSON object.")
        subject = entry.get("subject")
        if not subject or not isinstance(subject, str):
            raise ValueError("Missing 'subject'.")
        try:
            event_type = StudyEventType(entry.get("event_type"))
        except ValueError:
            raise ValueError(f"Invalid 'event_type': {entry.get('event_type')!r}.")
        weekday = Weekday.from_code(entry.get("day_of_week"))
        if weekday is None:
            raise ValueError(f"Invalid 'day_of_week': {entry.get('day_of_week')!r}.")
        start_time = parse_time(entry.get("start_time"))
        end_time = parse_time(entry.get("end_time"))
        if start_time is None or end_time is None:
            raise ValueError(f"Times must match {TIME_FORMAT}.")
        if end_time <= start_time:
            raise ValueError("'end_time' must be later than 'start_time'.")

        events.append(
            StudyEvent(
                id=None,
                subject_name=subject.strip(),
                event_type=event_type,
                weekday=weekday,
                start_time=start_time,
                end_time=end_time,
                room=entry.get("room"),
                is_mandatory=bool(entry.get("is_mandatory", True)),
            )
        )
    return events


# Backwards-compatible import name; the adapter is shared by both AI providers.
GeminiScheduleRecognizer = ScheduleRecognizer
