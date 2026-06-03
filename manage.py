"""
Punto de entrada para comandos de gestión de Flask.

Uso:
    flask --app manage db init       # Inicializar carpeta migrations/
    flask --app manage db migrate -m "descripción"
    flask --app manage db upgrade    # Aplicar migraciones pendientes
    flask --app manage db downgrade  # Revertir última migración
"""
from app import app, db  # noqa: F401 — expone la instancia para flask-migrate
