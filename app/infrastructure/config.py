import configparser
import os
from datetime import date

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_PATH = os.path.join(_ROOT, "config.ini")


def _load_dotenv(path: str) -> None:
    """Minimal .env reader for running without Docker; never overrides existing env vars."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _parse_semester_starts(value: str) -> list[tuple[int, int]]:
    """"09-01,02-01" -> [(9, 1), (2, 1)] (month-day pairs; the same every year)."""
    starts = []
    for part in value.split(","):
        try:
            month, day = (int(piece) for piece in part.strip().split("-"))
            date(2000, month, day)
        except ValueError:
            raise RuntimeError(f"SEMESTER_START_DATES must look like '09-01,02-01', got {value!r}.")
        starts.append((month, day))
    return starts


class Settings:
    """Application settings. Environment variables (.env / Docker) take precedence over config.ini (N-22)."""

    def __init__(self, path: str = _CONFIG_PATH):
        _load_dotenv(os.path.join(_ROOT, ".env"))

        parser = configparser.ConfigParser()
        parser.read(path)

        def get(env: str, section: str, option: str, fallback: str | None = None) -> str:
            value = os.environ.get(env)
            if value is not None and value != "":
                return value
            if parser.has_option(section, option):
                return parser.get(section, option)
            if fallback is not None:
                return fallback
            raise RuntimeError(
                f"Missing configuration: set {env} (.env) or [{section}] {option} (config.ini)."
            )

        self.db_host = get("DB_HOST", "database", "host", "localhost")
        self.db_port = int(get("DB_PORT", "database", "port", "5432"))
        self.db_name = get("DB_NAME", "database", "name")
        self.db_user = get("DB_USER", "database", "user")
        self.db_password = get("DB_PASSWORD", "database", "password")

        self.gemini_api_key = get("GEMINI_API_KEY", "gemini", "api_key", "")
        self.gemini_model = get("GEMINI_MODEL", "gemini", "model", "gemini-3.5-flash")
        self.ai_provider = get("AI_PROVIDER", "ai", "provider", "gemini").strip().lower()
        if self.ai_provider not in {"gemini", "claude"}:
            raise RuntimeError("AI_PROVIDER must be either 'gemini' or 'claude'.")
        self.claude_api_key = get("CLAUDE_API_KEY", "claude", "api_key", "")
        self.claude_model = get("CLAUDE_MODEL", "claude", "model", "claude-sonnet-4-5-20250929")

        # Google Calendar (sprint 2). Optional: without them the app runs and the calendar window explains
        # that the integration is not configured.
        self.google_client_id = get("GOOGLE_CLIENT_ID", "google", "client_id", "")
        self.google_client_secret = get("GOOGLE_CLIENT_SECRET", "google", "client_secret", "")
        self.google_redirect_uri = get(
            "GOOGLE_REDIRECT_URI", "google", "redirect_uri", "http://127.0.0.1:5000/calendar/callback"
        )
        self.token_encryption_key = get("TOKEN_ENCRYPTION_KEY", "google", "token_encryption_key", "")

        self.semester_start_dates = _parse_semester_starts(
            get("SEMESTER_START_DATES", "reminders", "semester_start_dates", "09-01,02-01")
        )

        self.secret_key = get("SECRET_KEY", "app", "secret_key")
        self.debug = get("FLASK_DEBUG", "app", "debug", "false").lower() == "true"
