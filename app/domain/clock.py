"""The system's notion of "now": local time of the university (Europe/Vilnius), independent of the host's time zone.

The database session uses the same time zone (see infrastructure/database.py), so timestamps written by
PostgreSQL's now() and by the application can be compared.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.domain.rules import LOCAL_TIMEZONE

_ZONE = ZoneInfo(LOCAL_TIMEZONE)


def local_now() -> datetime:
    """Current local date and time without a time zone attached (like PostgreSQL TIMESTAMP)."""
    return datetime.now(_ZONE).replace(tzinfo=None)


def local_today() -> date:
    return local_now().date()
