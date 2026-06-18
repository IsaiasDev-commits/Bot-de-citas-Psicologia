"""
Fixtures compartidos para todos los tests de Equilibra.

Uso:
    pip install pytest
    pytest tests/ -v
"""
import os
import pytest

# Usar SQLite en memoria para tests — sin dependencias externas
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-not-for-production")


@pytest.fixture(scope="session")
def app():
    from app import app as flask_app
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )
    return flask_app


@pytest.fixture(scope="session")
def db(app):
    from models import db as _db
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture()
def client(app, db):
    with app.test_client() as c:
        yield c
