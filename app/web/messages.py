"""Lithuanian user-facing messages for the error codes produced by services."""

from app.domain.rules import MAX_PDF_SIZE_BYTES, MIN_PASSWORD_LENGTH

_MESSAGES = {
    ("name", "required"): "Vardas yra privalomas.",
    ("email", "required"): "El. paštas yra privalomas.",
    ("email", "invalid_format"): "Neteisingas el. pašto formatas.",
    ("email", "already_registered"): "Šis el. paštas jau užregistruotas.",
    ("password", "required"): "Slaptažodis yra privalomas.",
    ("password", "too_short"): f"Slaptažodis turi būti ne trumpesnis nei {MIN_PASSWORD_LENGTH} simboliai.",
    ("workplace_name", "required"): "Darbovietė yra privaloma.",
    ("weekday", "invalid_choice"): "Pasirinkite savaitės dieną.",
    ("day_of_week", "invalid_choice"): "Pasirinkite savaitės dieną.",
    ("subject", "required"): "Dalykas yra privalomas.",
    ("event_type", "invalid_choice"): "Pasirinkite įvykio tipą.",
    ("start_time", "invalid_time"): "Pradžios laikas turi būti formatu VV:MM.",
    ("end_time", "invalid_time"): "Pabaigos laikas turi būti formatu VV:MM.",
    ("end_time", "end_not_after_start"): "Pabaigos laikas turi būti vėlesnis už pradžios laiką.",
    ("file", "no_file"): "Pasirinkite PDF failą.",
    ("file", "not_pdf"): "Galima įkelti tik PDF formato failą.",
    ("file", "too_large"): f"Failo dydis negali viršyti {MAX_PDF_SIZE_BYTES // (1024 * 1024)} MB.",
    ("file", "consent_required"): "Prieš įkeldami failą patvirtinkite sutikimą siųsti jį DI paslaugos tiekėjui.",
}

LOGIN_FAILED = "Neteisingas el. paštas arba slaptažodis."
RECOGNITION_FAILED = "Nepavyko atpažinti tvarkaraščio. Bandykite įkelti failą iš naujo."


def translate(errors: dict[str, str]) -> dict[str, str]:
    """Map {field: code} to {field: Lithuanian message}."""
    return {field: _MESSAGES.get((field, code), code) for field, code in errors.items()}
