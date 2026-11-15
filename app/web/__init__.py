"""Web layer (Flask): HTTP routes and HTML templates. Contains no business logic."""

import logging

from flask import Flask, render_template
from werkzeug.exceptions import HTTPException

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

    from app.web import filters

    app.jinja_env.filters.update(
        initials=filters.initials,
        plural_lt=filters.plural_lt,
        event_type_label=filters.event_type_label,
        week_pattern_label=filters.week_pattern_label,
        local_datetime=filters.local_datetime,
        timeline=filters.timeline,
    )

    from app.web.auth.routes import auth_bp
    from app.web.calendar.routes import calendar_bp
    from app.web.home import home_bp
    from app.web.reminders.routes import reminders_bp
    from app.web.schedule.routes import schedule_bp
    from app.web.study_events.routes import study_events_bp
    from app.web.week.routes import week_bp
    from app.web.work_shifts.routes import work_shifts_bp

    for blueprint in (home_bp, auth_bp, schedule_bp, study_events_bp, work_shifts_bp, week_bp, reminders_bp, calendar_bp):
        app.register_blueprint(blueprint)

    @app.context_processor
    def inject_reminder():
        """The reminder bar (F-20) is shown on the schedule windows; a failure here must not break the page."""
        from flask import request

        from app.web.context import current_user_id

        user_id = current_user_id()
        if user_id is None or services.reminders is None or request.blueprint not in ("week", "schedule"):
            return {}
        try:
            return {"reminder": services.reminders.get_active_reminder(user_id)}
        except Exception:  # noqa: BLE001 - N-11: reminders are optional
            logging.getLogger(__name__).exception("Could not load the reminder")
            return {}

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """N-11: show an understandable message instead of crashing (e.g. database unavailable)."""
        if isinstance(error, HTTPException):
            return error
        logging.getLogger(__name__).exception("Unhandled error")
        return render_template("error.html"), 500

    return app
