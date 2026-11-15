"""Application-level errors.

Validation errors carry machine-readable codes (e.g. "required", "too_short");
the web layer translates them into Lithuanian messages.
"""


class ValidationFailed(Exception):
    """One or more fields are invalid. `errors` maps field name -> error code."""

    def __init__(self, errors: dict[str, str]):
        super().__init__(f"Validation failed: {errors}")
        self.errors = errors


class RowsValidationFailed(Exception):
    """Reviewed schedule rows are invalid. `errors` has one dict (field -> code) per row."""

    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("Schedule rows are invalid")
        self.errors = errors


class RecognitionFailed(Exception):
    """The recognizer could not read the timetable (F-05)."""

    def __init__(self, message: str, attempts: int):
        super().__init__(message)
        self.attempts = attempts


class AnalysisFailed(Exception):
    """The conflict analyzer did not return a valid result."""

    def __init__(self, message: str, attempts: int):
        super().__init__(message)
        self.attempts = attempts


class ReplaceConfirmationRequired(Exception):
    """The new schedule replaces the old one; nothing is changed until the user confirms (F-23)."""

    def __init__(self, event_count: int):
        super().__init__(f"{event_count} existing study events would be removed")
        self.event_count = event_count


class CalendarError(Exception):
    """A calendar operation failed. `code` is one of the constants below; the web layer translates it."""

    NOT_CONFIGURED = "NOT_CONFIGURED"  # Google settings are missing
    CONSENT_REQUIRED = "CONSENT_REQUIRED"  # the user did not agree to send data to Google
    NOT_CONNECTED = "NOT_CONNECTED"
    NOT_EXPORTED = "NOT_EXPORTED"  # nothing was exported yet, so there is nothing to update
    ACCESS_DENIED = "ACCESS_DENIED"  # the user refused access on Google's page
    INVALID_STATE = "INVALID_STATE"  # the OAuth state did not match (CSRF protection)
    INVALID_CODE = "INVALID_CODE"  # Google rejected the authorization code
    UNAVAILABLE = "UNAVAILABLE"  # network error, HTTP 5xx or 429 after the retries
    AUTH_EXPIRED = "AUTH_EXPIRED"  # tokens are no longer valid: the user must connect again
    NOT_FOUND = "NOT_FOUND"  # the Google event no longer exists
    REJECTED = "REJECTED"  # Google refused the request (HTTP 4xx)

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
