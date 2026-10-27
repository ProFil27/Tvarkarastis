from flask import Blueprint, render_template

gvs_bp = Blueprint("gvs", __name__)


@gvs_bp.route("/")
def index():
    # Placeholder pradinis puslapis. AK komponento dalis ja pakeicia
    # nukreipimu i /prisijungti arba /savaites-vaizdas, priklausomai nuo sesijos.
    return render_template("index.html")
