"""Business limits defined by the specification."""

MIN_PASSWORD_LENGTH = 8  # F-01
MAX_PDF_SIZE_BYTES = 10 * 1024 * 1024  # N-03
MAX_SUBJECT_LENGTH = 100  # F-17
MAX_ROOM_LENGTH = 50  # F-17
MAX_WORKPLACE_LENGTH = 100  # F-18
MAX_SHIFT_REPEATS = 60  # most weekly shifts created by one "repeat until" request
LOCAL_TIMEZONE = "Europe/Vilnius"  # times shown to the user and sent to the calendar (N-29, N-26)
SYNC_RETRY_DELAYS = (1, 2, 4)  # seconds to wait before each retry of a calendar request (N-31)
REMINDER_WINDOW_DAYS = 7  # F-20
SEMESTER_LENGTH_DAYS = 120  # TODO: replace with the real semester calendar
