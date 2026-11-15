from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.application.errors import ValidationFailed
from app.application.event_rows import ReviewRow
from app.domain.entities import StudyEventType, WeekPattern
from app.domain.weekday import Weekday
from app.web import messages
from app.web.context import current_user_id, login_required, services

study_events_bp = Blueprint("lectures", __name__, url_prefix="/lectures")

_EVENT_TYPE_CHOICES = [
    (StudyEventType.LECTURE.value, "Paskaita"),
    (StudyEventType.PRACTICAL.value, "Pratybos"),
    (StudyEventType.LABORATORY.value, "Laboratorinis darbas"),
]
_WEEKDAY_CHOICES = [(weekday.value, weekday.label) for weekday in Weekday]
_WEEK_PATTERN_CHOICES = [
    (WeekPattern.EVERY_WEEK.value, "Kiekvieną savaitę"),
    (WeekPattern.WEEK_1.value, "1 savaitė"),
    (WeekPattern.WEEK_2.value, "2 savaitė"),
]
_EMPTY_FORM = ReviewRow("", StudyEventType.LECTURE.value, Weekday.MONDAY.value, "", "", "", True).to_dict()


def _render(form: dict, errors: dict, editing_id: int | None = None):
    return render_template(
        "lectures.html",
        events=services().study_events.list_events(current_user_id()),
        form=form,
        errors=errors,
        editing_id=editing_id,
        event_type_choices=_EVENT_TYPE_CHOICES,
        weekday_choices=_WEEKDAY_CHOICES,
        week_pattern_choices=_WEEK_PATTERN_CHOICES,
    )


def _form_row() -> ReviewRow:
    return ReviewRow(
        subject=request.form.get("subject", ""),
        event_type=request.form.get("event_type", ""),
        day_of_week=request.form.get("day_of_week", ""),
        start_time=request.form.get("start_time", ""),
        end_time=request.form.get("end_time", ""),
        room=request.form.get("room", ""),
        is_mandatory=request.form.get("is_mandatory") == "on",
        week_pattern=request.form.get("week_pattern", WeekPattern.EVERY_WEEK.value),
    )


@study_events_bp.route("/", methods=["GET"])
@login_required
def list_events():
    return _render(_EMPTY_FORM, {})


@study_events_bp.route("/", methods=["POST"])
@login_required
def add_event():
    row = _form_row()
    try:
        services().study_events.add_event(current_user_id(), row)
    except ValidationFailed as exc:
        return _render(row.to_dict(), messages.translate(exc.errors))
    flash("Paskaita pridėta.", "success")
    return redirect(url_for("lectures.list_events"))


@study_events_bp.route("/<int:event_id>/edit", methods=["GET"])
@login_required
def edit_event(event_id):
    event = services().study_events.get_event(current_user_id(), event_id)
    if event is None:
        flash("Paskaita nerasta.", "error")
        return redirect(url_for("lectures.list_events"))
    return _render(ReviewRow.from_event(event).to_dict(), {}, event_id)


@study_events_bp.route("/<int:event_id>/edit", methods=["POST"])
@login_required
def save_event(event_id):
    row = _form_row()
    try:
        event = services().study_events.update_event(current_user_id(), event_id, row)
    except ValidationFailed as exc:
        return _render(row.to_dict(), messages.translate(exc.errors), event_id)
    if event is None:
        flash("Paskaita nerasta.", "error")
    else:
        flash("Paskaita išsaugota.", "success")
    return redirect(url_for("lectures.list_events"))


@study_events_bp.route("/<int:event_id>/remove", methods=["GET"])
@login_required
def confirm_remove(event_id):
    """Removing data is irreversible, so it is confirmed on a separate page."""
    event = services().study_events.get_event(current_user_id(), event_id)
    if event is None:
        flash("Paskaita nerasta.", "error")
        return redirect(url_for("lectures.list_events"))
    return render_template("lecture_remove.html", event=event)


@study_events_bp.route("/<int:event_id>/remove", methods=["POST"])
@login_required
def remove_event(event_id):
    if services().study_events.remove_event(current_user_id(), event_id):
        flash("Paskaita pašalinta.", "success")
    else:
        flash("Paskaita nerasta.", "error")
    return redirect(url_for("lectures.list_events"))
