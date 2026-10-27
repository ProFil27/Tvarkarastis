"""Weekday value object.

Enum values are the ASCII codes stored in the database (see db/schema.sql); the
label is the Lithuanian display name shown to users (N-07).
"""

from enum import Enum


class Weekday(Enum):
    MONDAY = "PIRMADIENIS"
    TUESDAY = "ANTRADIENIS"
    WEDNESDAY = "TRECIADIENIS"
    THURSDAY = "KETVIRTADIENIS"
    FRIDAY = "PENKTADIENIS"
    SATURDAY = "SESTADIENIS"
    SUNDAY = "SEKMADIENIS"

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def index(self) -> int:
        """0 for Monday ... 6 for Sunday."""
        return list(Weekday).index(self)

    @classmethod
    def from_label(cls, label: str) -> "Weekday | None":
        for weekday in cls:
            if weekday.label == label:
                return weekday
        return None

    @classmethod
    def from_code(cls, code: str) -> "Weekday | None":
        try:
            return cls(code)
        except ValueError:
            return None


_LABELS = {
    Weekday.MONDAY: "Pirmadienis",
    Weekday.TUESDAY: "Antradienis",
    Weekday.WEDNESDAY: "Trečiadienis",
    Weekday.THURSDAY: "Ketvirtadienis",
    Weekday.FRIDAY: "Penktadienis",
    Weekday.SATURDAY: "Šeštadienis",
    Weekday.SUNDAY: "Sekmadienis",
}
