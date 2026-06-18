from constants import utcnow
from datetime import datetime
from urllib.parse import urlparse, urljoin
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from models import User, db
from . import admin_bp


def _is_safe_redirect_url(target: str) -> bool:
    """Verifica que el redirect apunte al mismo host (previene Open Redirect)."""
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not email or not password:
            flash("Por favor completa todos los campos.", "error")
            return render_template("login.html")

        user = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()

        if user and user.is_active and user.check_password(password):
            user.last_login = utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            if not _is_safe_redirect_url(next_page):
                next_page = None
            return redirect(next_page or url_for("admin.dashboard"))

        flash("Correo o contraseña incorrectos.", "error")

    return render_template("login.html")


@admin_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("admin.login"))
