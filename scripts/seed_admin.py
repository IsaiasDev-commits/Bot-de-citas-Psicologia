"""
Crea el usuario administrador inicial.

Uso:
    python scripts/seed_admin.py

Variables de entorno (opcionales, tienen valores por defecto para desarrollo):
    ADMIN_EMAIL     — correo del admin (default: admin@equilibra.com)
    ADMIN_PASSWORD  — contraseña     (default: Equilibra2025!)
    ADMIN_NAME      — nombre         (default: Administrador)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import app
from models import db, User


def seed():
    email = os.getenv("ADMIN_EMAIL", "admin@equilibra.com")
    password = os.getenv("ADMIN_PASSWORD", "Equilibra2025!")
    name = os.getenv("ADMIN_NAME", "Administrador")

    with app.app_context():
        db.create_all()

        existing = User.query.filter_by(email=email).first()
        if existing:
            print(f"[INFO] Usuario ya existe: {email}")
            return

        user = User(email=email, name=name, role="admin", is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"[OK] Usuario admin creado:")
        print(f"   Email:    {email}")
        print(f"   Password: {password}")
        print(f"   Rol:      admin")
        print()
        print("Accede al panel en: http://localhost:5000/admin/login")


if __name__ == "__main__":
    seed()
