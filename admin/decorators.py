from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user


def admin_required(f):
    """Solo administradores (role='admin') pueden acceder."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("admin.login"))
        if not current_user.is_active:
            flash("Tu cuenta está desactivada.", "error")
            return redirect(url_for("admin.login"))
        if not current_user.is_admin():
            flash("Acceso restringido a administradores.", "error")
            return redirect(url_for("admin.dashboard"))
        return f(*args, **kwargs)
    return decorated


def login_required_admin(f):
    """Cualquier usuario activo del panel (admin o psicólogo) puede acceder."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("admin.login"))
        if not current_user.is_active:
            flash("Tu cuenta está desactivada.", "error")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated
