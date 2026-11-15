from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, request, url_for

from app.web.context import current_user_id, login_required, services

reminders_bp = Blueprint("reminders", __name__, url_prefix="/reminders")


def _back():
    """Return to the page the button was on (only local paths are accepted)."""
    target = request.form.get("next", "")
    parsed = urlparse(target)
    if target.startswith("/") and not target.startswith("//") and not parsed.netloc:
        return redirect(target)
    return redirect(url_for("week.view"))


@reminders_bp.route("/close", methods=["POST"])
@login_required
def close():
    services().reminders.close(current_user_id())
    return _back()


@reminders_bp.route("/disable", methods=["POST"])
@login_required
def disable():
    services().reminders.disable(current_user_id())
    flash("Priminimai išjungti. Juos galima vėl įjungti kalendoriaus lange.", "success")
    return _back()


@reminders_bp.route("/enable", methods=["POST"])
@login_required
def enable():
    services().reminders.enable(current_user_id())
    flash("Priminimai įjungti.", "success")
    return _back()
