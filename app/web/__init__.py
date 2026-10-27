"""Web layer (Flask): HTTP routes and HTML templates. Contains no business logic."""

from flask import Flask

from app.container import Services, build_services
from app.infrastructure.config import Settings


def create_app(settings: Settings | None = None, services: Services | None = None) -> Flask:
    """Application factory. Pass `services` to run the web layer with fake services (tests)."""
    if services is None:
        settings = settings or Settings()
        services = build_services(settings)

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = settings.secret_key if settings else "test-secret-key"
    app.config["DEBUG_MODE"] = settings.debug if settings else False
    app.extensions["services"] = services

    from app.web.home import home_bp

    app.register_blueprint(home_bp)

    from app.web.auth.routes import auth_bp

    app.register_blueprint(auth_bp)

    from app.web.schedule.routes import schedule_bp

    app.register_blueprint(schedule_bp)

# @web:work_shifts

    from app.web.week.routes import week_bp

    app.register_blueprint(week_bp)

    return app
