from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.application.errors import RecognitionFailed, RowsValidationFailed, ValidationFailed
from app.application.schedule_import_service import ReviewRow
from app.domain.entities import StudyEventType
from app.domain.weekday import Weekday
from app.web import messages
from app.web.context import current_user_id, login_required, services

schedule_bp = Blueprint("schedule", __name__, url_prefix="/schedule")

_PENDING_ROWS = "pending_review_rows"
_PENDING_PDF_ID = "pending_pdf_document_id"

_EVENT_TYPE_CHOICES = [
    (StudyEventType.LECTURE.value, "Paskaita"),
    (StudyEventType.PRACTICAL.value, "Pratybos"),
    (StudyEventType.LABORATORY.value, "Laboratoriniai darbai"),
]
_WEEKDAY_CHOICES = [(weekday.value, weekday.label) for weekday in Weekday]


def _render_review(rows: list[dict], errors: list[dict]):
    return render_template(
        "review.html",
        entries=rows,
        errors=errors,
        weekday_choices=_WEEKDAY_CHOICES,
        event_type_choices=_EVENT_TYPE_CHOICES,
    )


def _clear_pending() -> None:
    session.pop(_PENDING_ROWS, None)
    session.pop(_PENDING_PDF_ID, None)


@schedule_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        return render_template("upload.html", error=None)

    pdf_file = request.files.get("pdf_file")
    if pdf_file is None or pdf_file.filename == "":
        return render_template("upload.html", error=messages.translate({"file": "no_file"})["file"])

    try:
        result = services().schedule_import.upload_and_recognize(
            current_user_id(), pdf_file.filename, pdf_file.read(), request.form.get("ai_consent") == "on"
        )
    except ValidationFailed as exc:
        return render_template("upload.html", error=messages.translate(exc.errors)["file"])
    except RecognitionFailed:
        return render_template("upload.html", error=messages.RECOGNITION_FAILED)

    session[_PENDING_ROWS] = [row.to_dict() for row in result.rows]
    session[_PENDING_PDF_ID] = result.pdf_document_id
    return redirect(url_for("schedule.review"))


@schedule_bp.route("/review", methods=["GET"])
@login_required
def review():
    rows = session.get(_PENDING_ROWS)
    if not rows:
        flash("Nėra atpažintų duomenų peržiūrai. Pirmiausia įkelkite tvarkaraštį.", "error")
        return redirect(url_for("schedule.upload"))
    return _render_review(rows, [{} for _ in rows])


@schedule_bp.route("/review", methods=["POST"])
@login_required
def submit_review():
    pdf_document_id = session.get(_PENDING_PDF_ID)
    if pdf_document_id is None:
        flash("Sesija baigėsi, įkelkite tvarkaraštį iš naujo.", "error")
        return redirect(url_for("schedule.upload"))

    if request.form.get("action") == "reject":
        services().schedule_import.reject(pdf_document_id)
        _clear_pending()
        flash("Atpažinti duomenys atmesti.", "success")
        return redirect(url_for("schedule.upload"))

    rows = [
        ReviewRow(
            subject=request.form.get(f"subject_{i}", ""),
            event_type=request.form.get(f"event_type_{i}", ""),
            day_of_week=request.form.get(f"day_of_week_{i}", ""),
            start_time=request.form.get(f"start_time_{i}", ""),
            end_time=request.form.get(f"end_time_{i}", ""),
            room=request.form.get(f"room_{i}", ""),
            is_mandatory=request.form.get(f"is_mandatory_{i}") == "on",
        )
        for i in range(int(request.form.get("row_count", 0)))
    ]

    try:
        services().schedule_import.confirm(current_user_id(), pdf_document_id, rows)
    except RowsValidationFailed as exc:
        return _render_review([row.to_dict() for row in rows], [messages.translate(e) for e in exc.errors])

    _clear_pending()
    flash("Tvarkaraštis išsaugotas.", "success")
    return redirect(url_for("home.index"))
