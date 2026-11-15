from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.application.errors import CalendarError
from app.web import messages
from app.web.context import current_user_id, login_required, services

calendar_bp = Blueprint("calendar", __name__, url_prefix="/calendar")

_OAUTH_STATE = "calendar_oauth_state"
_OAUTH_VERIFIER = "calendar_oauth_verifier"


@calendar_bp.route("/", methods=["GET"])
@login_required
def view():
    user_id = current_user_id()
    return render_template(
        "calendar.html",
        report=services().calendar.status(user_id),
        available=services().calendar.is_available(),
        reminders_enabled=services().reminders.is_enabled(user_id) if services().reminders else True,
        operation_labels=messages.OPERATION_LABELS,
        error_text=messages.calendar_error,
    )


@calendar_bp.route("/connect", methods=["POST"])
@login_required
def connect():
    """Send the user to Google's approval page (F-24). The state ties the answer to this session (N-44)."""
    try:
        request_data = services().calendar.begin_connect(current_user_id(), request.form.get("consent") == "on")
    except CalendarError as exc:
        flash(messages.calendar_error(exc.code), "error")
        return redirect(url_for("calendar.view"))
    session[_OAUTH_STATE] = request_data.state
    session[_OAUTH_VERIFIER] = request_data.code_verifier
    return redirect(request_data.url)


@calendar_bp.route("/callback", methods=["GET"])
@login_required
def callback():
    """Google sends the user back here with `code` and `state`, or with `error` (F-24, F-25)."""
    expected_state = session.pop(_OAUTH_STATE, None)  # one use only
    code_verifier = session.pop(_OAUTH_VERIFIER, None)
    try:
        services().calendar.complete_connect(
            current_user_id(),
            request.args.get("code"),
            request.args.get("state"),
            expected_state,
            code_verifier,
            request.args.get("error"),
        )
    except CalendarError as exc:
        flash(messages.calendar_error(exc.code), "error")
    else:
        flash("Google Calendar prijungtas.", "success")
    return redirect(url_for("calendar.view"))


@calendar_bp.route("/export", methods=["POST"])
@login_required
def export():
    """Export the schedule to Google Calendar in one step (F-26, F-27)."""
    try:
        result = services().calendar.export(current_user_id())
    except CalendarError as exc:
        flash(messages.calendar_error(exc.code), "error")
    else:
        flash(f"Eksportuota: {result.created} įrašų.", "success")
    return redirect(url_for("calendar.view"))


@calendar_bp.route("/reminders", methods=["POST"])
@login_required
def toggle_reminders():
    if request.form.get("enabled") == "on":
        services().reminders.enable(current_user_id())
    else:
        services().reminders.disable(current_user_id())
    return redirect(url_for("calendar.view"))
