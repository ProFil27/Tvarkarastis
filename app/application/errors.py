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
