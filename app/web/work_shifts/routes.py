from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.application.errors import ValidationFailed
from app.web import messages
from app.web.context import current_user_id, login_required, services

work_shifts_bp = Blueprint("work_shifts", __name__, url_prefix="/work-shifts")


def _render(errors: dict, form: dict, editing_id: int | None = None):
    shifts = services().work_shifts.list_shifts(current_user_id())
    return render_template("shifts.html", shifts=shifts, errors=errors, form=form, editing_id=editing_id)


def _form() -> dict:
    return {
        "workplace_name": request.form.get("workplace_name", ""),
        "work_date": request.form.get("work_date", ""),
        "start_time": request.form.get("start_time", ""),
        "end_time": request.form.get("end_time", ""),
        "repeat_until": request.form.get("repeat_until", "").strip(),
    }


@work_shifts_bp.route("/", methods=["GET"])
@login_required
def list_shifts():
    return _render({}, {})


@work_shifts_bp.route("/add", methods=["POST"])
@login_required
def add_shift():
    form = _form()
    arguments = (current_user_id(), form["workplace_name"], form["work_date"], form["start_time"], form["end_time"])
    try:
        if form["repeat_until"]:
            added = len(services().work_shifts.add_weekly_shifts(*arguments, form["repeat_until"]))
        else:
            services().work_shifts.add_shift(*arguments)
            added = 1
    except ValidationFailed as exc:
        return _render(messages.translate(exc.errors), form)

    flash("Darbo pamaina išsaugota." if added == 1 else f"Išsaugota pamainų: {added}.", "success")
    return redirect(url_for("work_shifts.list_shifts"))


@work_shifts_bp.route("/<int:shift_id>/edit", methods=["GET"])
@login_required
def edit_shift(shift_id):
    shift = services().work_shifts.get_shift(current_user_id(), shift_id)
    if shift is None:
        flash("Pamaina nerasta.", "error")
        return redirect(url_for("work_shifts.list_shifts"))
    form = {
        "workplace_name": shift.workplace_name,
        "work_date": shift.work_date.isoformat(),
        "start_time": shift.start_time.strftime("%H:%M"),
        "end_time": shift.end_time.strftime("%H:%M"),
    }
    return _render({}, form, shift_id)


@work_shifts_bp.route("/<int:shift_id>/edit", methods=["POST"])
@login_required
def save_shift(shift_id):
    form = _form()
    try:
        shift = services().work_shifts.update_shift(
            current_user_id(), shift_id, form["workplace_name"], form["work_date"], form["start_time"], form["end_time"]
        )
    except ValidationFailed as exc:
        return _render(messages.translate(exc.errors), form, shift_id)

    if shift is None:
        flash("Pamaina nerasta.", "error")
    else:
        flash("Darbo pamaina pakeista.", "success")
    return redirect(url_for("work_shifts.list_shifts"))


@work_shifts_bp.route("/<int:shift_id>/remove", methods=["POST"])
@login_required
def delete_shift(shift_id):
    if services().work_shifts.remove_shift(current_user_id(), shift_id):
        flash("Darbo pamaina pašalinta.", "success")
    else:
        flash("Pamaina nerasta.", "error")
    return redirect(url_for("work_shifts.list_shifts"))
