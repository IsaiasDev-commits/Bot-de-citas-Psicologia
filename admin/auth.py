from datetime import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from models import User, db
from . import admin_bp


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

        user = User.query.filter_by(email=email, is_active=True).first()

        if user and user.check_password(password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("admin.dashboard"))

        flash("Correo o contraseña incorrectos.", "error")

    return render_template("login.html")


@admin_bp.route("/logout")
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("admin.login"))
