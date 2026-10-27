"""Access to request-independent application objects from routes."""

from flask import current_app, redirect, session, url_for
from functools import wraps

from app.container import Services


def services() -> Services:
    return current_app.extensions["services"]


def current_user_id() -> int | None:
    return session.get("user_id")


def login_required(view):
    """Redirect anonymous users to the login page, so users only reach their own data (N-21)."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user_id() is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped
