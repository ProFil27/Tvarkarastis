import configparser
import os

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

        self.secret_key = get("SECRET_KEY", "app", "secret_key")
        self.debug = get("FLASK_DEBUG", "app", "debug", "false").lower() == "true"
