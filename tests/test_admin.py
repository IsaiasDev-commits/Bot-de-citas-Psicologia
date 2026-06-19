"""Tests de integración para el panel administrativo de Equilibra."""
import pytest
from datetime import datetime
from werkzeug.security import generate_password_hash


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def admin_user(db, app):
    """Crea un usuario administrador activo en la DB de test."""
    from models import User
    with app.app_context():
        u = User(
            name="Test Admin",
            email="testadmin@equilibra.com",
            is_active=True,
            role="admin",
        )
        u.set_password("TestPass123!")
        db.session.add(u)
        db.session.commit()
        yield u
        db.session.delete(u)
        db.session.commit()


@pytest.fixture()
def auth_client(client, admin_user):
    """Cliente HTTP ya autenticado como admin."""
    client.post(
        "/admin/login",
        data={"email": admin_user.email, "password": "TestPass123!"},
        follow_redirects=True,
    )
    return client


# ── login / logout ────────────────────────────────────────────────────────────

class TestAdminLogin:
    def test_login_page_accesible(self, client):
        r = client.get("/admin/login")
        assert r.status_code == 200

    def test_login_credenciales_incorrectas(self, client, admin_user):
        r = client.post(
            "/admin/login",
            data={"email": admin_user.email, "password": "wrong"},
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b"login" in r.data.lower() or b"incorrect" in r.data.lower() or r.request.path == "/admin/login"

    def test_login_exitoso_redirige_a_dashboard(self, client, admin_user):
        r = client.post(
            "/admin/login",
            data={"email": admin_user.email, "password": "TestPass123!"},
            follow_redirects=True,
        )
        assert r.status_code == 200

    def test_dashboard_sin_login_redirige(self, client):
        r = client.get("/admin/dashboard", follow_redirects=False)
        assert r.status_code in (301, 302)

    def test_dashboard_con_login_accesible(self, auth_client):
        r = auth_client.get("/admin/dashboard")
        assert r.status_code == 200


# ── rutas protegidas ──────────────────────────────────────────────────────────

class TestAdminProtectedRoutes:
    @pytest.mark.parametrize("path", [
        "/admin/dashboard",
        "/admin/patients",
        "/admin/appointments",
        "/admin/appointments/calendar",
        "/admin/stats",
    ])
    def test_ruta_sin_auth_redirige(self, client, path):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (301, 302)

    @pytest.mark.parametrize("path", [
        "/admin/dashboard",
        "/admin/patients",
        "/admin/appointments",
        "/admin/stats",
    ])
    def test_ruta_con_auth_accesible(self, auth_client, path):
        r = auth_client.get(path)
        assert r.status_code == 200


# ── API de citas ──────────────────────────────────────────────────────────────

class TestAdminAPI:
    def test_check_new_appointments_sin_auth(self, client):
        r = client.get("/admin/api/appointments/check-new")
        assert r.status_code in (301, 302, 401, 403)

    def test_check_new_appointments_con_auth(self, auth_client):
        r = auth_client.get("/admin/api/appointments/check-new")
        assert r.status_code == 200
        data = r.get_json()
        assert "count" in data
        assert "appointments" in data

    def test_update_status_cita_inexistente(self, auth_client):
        r = auth_client.patch(
            "/admin/api/appointments/99999/status",
            json={"status": "confirmed"},
            content_type="application/json",
        )
        assert r.status_code == 404

    def test_update_status_invalido(self, auth_client, db, app):
        from models import Patient, Appointment
        with app.app_context():
            p = Patient(name="Test Px", phone="0991111111")
            db.session.add(p)
            db.session.flush()
            a = Appointment(
                patient_id=p.id,
                scheduled_at=datetime(2026, 12, 1, 14, 0),
                symptom="Ansiedad",
                status="pending",
            )
            db.session.add(a)
            db.session.commit()
            appt_id = a.id

        r = auth_client.patch(
            f"/admin/api/appointments/{appt_id}/status",
            json={"status": "estado_inventado"},
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_update_status_exitoso(self, auth_client, db, app):
        from models import Patient, Appointment
        with app.app_context():
            p = Patient(name="Px Status", phone="0991111112")
            db.session.add(p)
            db.session.flush()
            a = Appointment(
                patient_id=p.id,
                scheduled_at=datetime(2026, 12, 2, 10, 0),
                status="pending",
            )
            db.session.add(a)
            db.session.commit()
            appt_id = a.id

        r = auth_client.patch(
            f"/admin/api/appointments/{appt_id}/status",
            json={"status": "confirmed"},
            content_type="application/json",
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["status"] == "confirmed"

    def test_update_appointment_notes(self, auth_client, db, app):
        from models import Patient, Appointment
        with app.app_context():
            p = Patient(name="Px Notes", phone="0991111113")
            db.session.add(p)
            db.session.flush()
            a = Appointment(
                patient_id=p.id,
                scheduled_at=datetime(2026, 12, 3, 10, 0),
                status="pending",
            )
            db.session.add(a)
            db.session.commit()
            appt_id = a.id

        r = auth_client.patch(
            f"/admin/api/appointments/{appt_id}/notes",
            json={"notes": "Paciente muestra mejora significativa."},
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True


# ── notas clínicas ────────────────────────────────────────────────────────────

class TestClinicalNotesAPI:
    @pytest.fixture()
    def patient_fixture(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Paciente Notas", phone="0993333310")
            db.session.add(p)
            db.session.commit()
            pid = p.id
        yield pid
        with app.app_context():
            from models import Patient, ClinicalNote
            ClinicalNote.query.filter_by(patient_id=pid).delete()
            Patient.query.filter_by(id=pid).delete()
            db.session.commit()

    def test_agregar_nota(self, auth_client, patient_fixture):
        r = auth_client.post(
            f"/admin/api/patients/{patient_fixture}/notes",
            json={"content": "Primera consulta. Paciente colaborador.", "is_private": True},
            content_type="application/json",
        )
        assert r.status_code == 201
        data = r.get_json()
        assert data["ok"] is True
        assert "note" in data
        assert data["note"]["content"] == "Primera consulta. Paciente colaborador."

    def test_agregar_nota_vacia_retorna_400(self, auth_client, patient_fixture):
        r = auth_client.post(
            f"/admin/api/patients/{patient_fixture}/notes",
            json={"content": "   "},
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_agregar_nota_paciente_inexistente(self, auth_client):
        r = auth_client.post(
            "/admin/api/patients/99999/notes",
            json={"content": "Nota para paciente que no existe"},
            content_type="application/json",
        )
        assert r.status_code == 404

    def test_nota_demasiado_larga_retorna_400(self, auth_client, patient_fixture):
        r = auth_client.post(
            f"/admin/api/patients/{patient_fixture}/notes",
            json={"content": "x" * 10_001},
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_actualizar_nota(self, auth_client, patient_fixture, db, app):
        # Crear nota
        r = auth_client.post(
            f"/admin/api/patients/{patient_fixture}/notes",
            json={"content": "Nota original"},
            content_type="application/json",
        )
        note_id = r.get_json()["note"]["id"]

        # Actualizar
        r = auth_client.put(
            f"/admin/api/patients/{patient_fixture}/notes/{note_id}",
            json={"content": "Nota actualizada"},
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.get_json()["note"]["content"] == "Nota actualizada"

    def test_eliminar_nota(self, auth_client, patient_fixture):
        # Crear nota
        r = auth_client.post(
            f"/admin/api/patients/{patient_fixture}/notes",
            json={"content": "Nota para borrar"},
            content_type="application/json",
        )
        note_id = r.get_json()["note"]["id"]

        # Eliminar
        r = auth_client.delete(
            f"/admin/api/patients/{patient_fixture}/notes/{note_id}",
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_sin_auth_retorna_redireccion(self, client, patient_fixture):
        r = client.post(
            f"/admin/api/patients/{patient_fixture}/notes",
            json={"content": "Intento sin auth"},
            content_type="application/json",
        )
        assert r.status_code in (301, 302, 401, 403)
