"""User-facing (Lithuanian) texts for calendar errors, shared by the web layer and the system notifications (F-25, F-31).

Each text names the cause and the next step.
"""

from app.application.errors import CalendarError

CALENDAR_ERROR_TEXTS = {
    CalendarError.NOT_CONFIGURED: "Google Calendar nesukonfigūruotas. Kreipkitės į sistemos administratorių.",
    CalendarError.CONSENT_REQUIRED: "Prieš prijungdami kalendorių patvirtinkite sutikimą siųsti duomenis į Google.",
    CalendarError.NOT_CONNECTED: "Google Calendar neprijungtas. Pirmiausia prijunkite paskyrą.",
    CalendarError.NOT_EXPORTED: "Tvarkaraštis dar neeksportuotas. Pirmiausia eksportuokite jį į Google Calendar.",
    CalendarError.ACCESS_DENIED: "Prieiga nepatvirtinta. Kalendorius neprijungtas.",
    CalendarError.INVALID_STATE: "Neteisingas užklausos kodas. Bandykite prijungti kalendorių dar kartą.",
    CalendarError.INVALID_CODE: "Neteisingas užklausos kodas. Bandykite prijungti kalendorių dar kartą.",
    CalendarError.UNAVAILABLE: "Kalendoriaus tiekėjas nepasiekiamas. Bandykite dar kartą.",
    CalendarError.AUTH_EXPIRED: "Prisijunkite prie Google Calendar iš naujo.",
    CalendarError.NOT_FOUND: "Kalendoriaus įvykis nerastas. Bandykite sinchronizuoti dar kartą.",
    CalendarError.REJECTED: "Kalendoriaus tiekėjas atmetė užklausą. Bandykite dar kartą.",
}


def calendar_error_text(code: str) -> str:
    return CALENDAR_ERROR_TEXTS.get(code, CALENDAR_ERROR_TEXTS[CalendarError.UNAVAILABLE])
