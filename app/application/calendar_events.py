"""Google Calendar `Event` resources (JSON, UTF-8) built from study events and work shifts (F-26, N-26).

Study events become weekly recurring events for the schedule's validity period; work shifts become single events.
Times are local (Europe/Vilnius) and sent to the minute (N-29).
"""

from datetime import date, datetime, time, timedelta

from app.domain.academic_week import pattern_applies
from app.domain.entities import StudyEvent, StudyEventType, WeekPattern, WorkShift
from app.domain.rules import LOCAL_TIMEZONE

MAX_SUMMARY_LENGTH = 1024  # N-26

_TYPE_LABELS = {
    StudyEventType.LECTURE: "paskaita",
    StudyEventType.PRACTICAL: "pratybos",
    StudyEventType.LABORATORY: "laboratorinis darbas",
}
_WEEK_LABELS = {WeekPattern.WEEK_1: "1 savaitė", WeekPattern.WEEK_2: "2 savaitė"}


def first_occurrence(event: StudyEvent, fallback_start: date) -> date | None:
    """First date on or after the schedule's start that has the event's weekday and a study week it runs in.

    None if there is no such date inside the validity period (the event is then not exported).
    """
    start = event.valid_from or fallback_start
    day = start + timedelta(days=(event.weekday.index - start.weekday()) % 7)
    for _ in range(2):  # the matching weekday of the next week covers week 1 / week 2 alternation
        if pattern_applies(event.week_pattern, day):
            break
        day += timedelta(days=7)
    else:
        return None
    if event.valid_to is not None and day > event.valid_to:
        return None
    return day


def _date_time(day: date, value: time) -> dict:
    return {"dateTime": datetime.combine(day, value).strftime("%Y-%m-%dT%H:%M:00"), "timeZone": LOCAL_TIMEZONE}


def study_event_body(event: StudyEvent, fallback_start: date) -> dict | None:
    """The Google event for a study event, or None if it never takes place in its validity period."""
    day = first_occurrence(event, fallback_start)
    if day is None:
        return None
    rule = "RRULE:FREQ=WEEKLY"
    if event.week_pattern != WeekPattern.EVERY_WEEK:
        rule += ";INTERVAL=2"  # week 1 / week 2 lectures happen every second week
    if event.valid_to is not None:
        rule += f";UNTIL={event.valid_to.strftime('%Y%m%d')}T235959Z"

    description = [_TYPE_LABELS[event.event_type].capitalize()]
    if event.week_pattern in _WEEK_LABELS:
        description.append(_WEEK_LABELS[event.week_pattern])
    if not event.is_mandatory:
        description.append("neprivaloma")
    body = {
        "summary": f"{event.subject_name} ({_TYPE_LABELS[event.event_type]})"[:MAX_SUMMARY_LENGTH],
        "description": ", ".join(description),
        "start": _date_time(day, event.start_time),
        "end": _date_time(day, event.end_time),
        "recurrence": [rule],
    }
    if event.room:
        body["location"] = event.room
    return body


def work_shift_body(shift: WorkShift) -> dict:
    """The Google event for a work shift: a single event on its date."""
    return {
        "summary": f"Darbas: {shift.workplace_name}"[:MAX_SUMMARY_LENGTH],
        "description": "Darbo pamaina",
        "location": shift.workplace_name,
        "start": _date_time(shift.work_date, shift.start_time),
        "end": _date_time(shift.work_date, shift.end_time),
    }


def shift_series_body(workplace_name: str, start: time, end: time, dates: list[date]) -> dict:
    """One Google event for a weekly series of work shifts.

    `dates` are the days the shifts take place. The event repeats every week from the first to the last of them;
    weeks in between that have no shift (removed or changed on their own) are excluded with EXDATE.
    """
    days = sorted(dates)
    first, last = days[0], days[-1]
    body = {
        "summary": f"Darbas: {workplace_name}"[:MAX_SUMMARY_LENGTH],
        "description": "Darbo pamaina",
        "location": workplace_name,
        "start": _date_time(first, start),
        "end": _date_time(first, end),
    }
    if len(days) > 1:
        present = set(days)
        weeks = (first + timedelta(weeks=n) for n in range((last - first).days // 7 + 1))
        gaps = [day for day in weeks if day not in present]
        body["recurrence"] = [f"RRULE:FREQ=WEEKLY;UNTIL={last.strftime('%Y%m%d')}T235959Z"] + [
            f"EXDATE;TZID={LOCAL_TIMEZONE}:{day.strftime('%Y%m%d')}T{start.strftime('%H%M')}00" for day in gaps
        ]
    return body
