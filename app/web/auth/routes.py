from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.application.errors import ValidationFailed
from app.web import messages
from app.web.context import services

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", errors={}, form={})

    name = request.form.get("name", "")
    email = request.form.get("email", "")
    try:
        user = services().auth.register(
            name, email, request.form.get("password", ""), request.form.get("ai_consent") == "on"
        )
    except ValidationFailed as exc:
        return render_template(
            "register.html", errors=messages.translate(exc.errors), form={"name": name, "email": email}
        )

    session["user_id"] = user.id
    session["user_name"] = user.name
    flash("Registracija sėkminga.", "success")
    return redirect(url_for("home.index"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None, form={})

    email = request.form.get("email", "")
    user = services().auth.authenticate(email, request.form.get("password", ""))
    if user is None:
        return render_template("login.html", error=messages.LOGIN_FAILED, form={"email": email})

    session["user_id"] = user.id
    session["user_name"] = user.name
    return redirect(url_for("home.index"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Atsijungta.", "success")
    return redirect(url_for("home.index"))
