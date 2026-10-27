from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.application.errors import ValidationFailed
from app.domain.weekday import Weekday
from app.web import messages
from app.web.context import current_user_id, login_required, services

work_shifts_bp = Blueprint("work_shifts", __name__, url_prefix="/work-shifts")

_WEEKDAY_LABELS = [weekday.label for weekday in Weekday]


def _render(errors: dict, form: dict):
    shifts = services().work_shifts.list_shifts(current_user_id())
    return render_template("shifts.html", shifts=shifts, weekday_labels=_WEEKDAY_LABELS, errors=errors, form=form)


@work_shifts_bp.route("/", methods=["GET"])
@login_required
def list_shifts():
    return _render({}, {})


@work_shifts_bp.route("/add", methods=["POST"])
@login_required
def add_shift():
    form = {
        "workplace_name": request.form.get("workplace_name", ""),
        "day_of_week": request.form.get("day_of_week", ""),
        "start_time": request.form.get("start_time", ""),
        "end_time": request.form.get("end_time", ""),
    }
    try:
        services().work_shifts.add_shift(
            current_user_id(),
            form["workplace_name"],
            Weekday.from_label(form["day_of_week"]),
            form["start_time"],
            form["end_time"],
        )
    except ValidationFailed as exc:
        return _render(messages.translate(exc.errors), form)

    flash("Darbo pamaina išsaugota.", "success")
    return redirect(url_for("work_shifts.list_shifts"))


@work_shifts_bp.route("/<int:shift_id>/remove", methods=["POST"])
@login_required
def delete_shift(shift_id):
    if services().work_shifts.remove_shift(current_user_id(), shift_id):
        flash("Darbo pamaina pašalinta.", "success")
    else:
        flash("Pamaina nerasta.", "error")
    return redirect(url_for("work_shifts.list_shifts"))
