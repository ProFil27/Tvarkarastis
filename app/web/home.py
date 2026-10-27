from flask import Blueprint, redirect, url_for

from app.web.context import current_user_id

home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def index():
    """Landing: the week view for signed-in users, the login page for everyone else."""
    if current_user_id() is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for("week.view"))
