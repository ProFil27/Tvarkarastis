from datetime import date, datetime

from flask import Blueprint, redirect, render_template, url_for

from app.web.context import current_user_id, login_required, services

week_bp = Blueprint("week", __name__, url_prefix="/week")


def _parse_week(value: str | None) -> date:
    """Accept YYYY-MM-DD (N-07); an invalid or empty value falls back to today."""
    try:
        return datetime.strptime(value or "", "%Y-%m-%d").date()
    except ValueError:
        return date.today()


@week_bp.route("/", defaults={"week": None})
@week_bp.route("/<week>")
@login_required
def view(week):
    user_id = current_user_id()
    return render_template(
        "week_view.html",
        week=services().week_view.get_week(user_id, _parse_week(week)),
        notifications=services().week_view.unread_notifications(user_id),
    )


@week_bp.route("/notifications/<int:notification_id>/dismiss", methods=["POST"])
@login_required
def dismiss_notification(notification_id):
    services().week_view.dismiss_notification(current_user_id(), notification_id)
    return redirect(url_for("week.view"))
