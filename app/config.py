import configparser
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini")


class Config:
    def __init__(self, path: str = _CONFIG_PATH):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Nerastas konfiguracijos failas: {path}. "
                "Nukopijuokite config.example.ini -> config.ini ir uzpildykite reiksmes."
            )
        parser = configparser.ConfigParser()
        parser.read(path)

        self.db_host = parser.get("database", "host")
        self.db_port = parser.getint("database", "port")
        self.db_name = parser.get("database", "name")
        self.db_user = parser.get("database", "user")
        self.db_password = parser.get("database", "password")

        self.gemini_api_key = parser.get("gemini", "api_key", fallback="")
        self.gemini_model = parser.get("gemini", "model", fallback="gemini-1.5-flash")

        self.secret_key = parser.get("app", "secret_key")
        self.debug = parser.getboolean("app", "debug", fallback=False)
