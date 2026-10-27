from flask import Flask

from app.config import Config
from app.dpk import db as dpk_db


def create_app() -> Flask:
    config = Config()

    app = Flask(__name__, template_folder="gvs/templates", static_folder="gvs/static")
    app.secret_key = config.secret_key
    app.config["APP_CONFIG"] = config

    dpk_db.init_pool(config)

    # Kiekviena komandos dalis registruoja sava blueprint'a cia.
    # Pvz.: from app.ak.routes import ak_bp; app.register_blueprint(ak_bp)
    from app.gvs.routes import gvs_bp

    app.register_blueprint(gvs_bp)

    return app
