from flask import Blueprint

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="../templates/admin",
)

from . import auth, routes, api  # noqa: F401, E402
