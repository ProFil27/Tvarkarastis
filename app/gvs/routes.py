from flask import Blueprint, render_template

gvs_bp = Blueprint("gvs", __name__)


@gvs_bp.route("/")
def index():
    # Placeholder landing page.
    return render_template("index.html")
