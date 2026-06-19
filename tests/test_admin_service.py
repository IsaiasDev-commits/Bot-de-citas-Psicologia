"""Tests for services/admin_service.py — business logic layer."""
import pytest
from datetime import datetime


# ---------------------------------------------------------------------------
# find_or_create_patient
# ---------------------------------------------------------------------------

class TestFindOrCreatePatient:
    # Phone numbers in 0999-88xx range to avoid conflicts with other test files

    def _cleanup(self, db, app, phone):
        from models import Patient
        with app.app_context():
            p = Patient.query.filter_by(phone=phone).first()
            if p:
                db.session.delete(p)
                db.session.commit()

    def test_creates_new_patient(self, db, app):
        from services.admin_service import find_or_create_patient
        phone = "0999880001"
        with app.app_context():
            p = find_or_create_patient("Test User", phone)
            db.session.commit()
            assert p.id is not None
            assert p.name == "Test User"
            assert p.phone == phone
        self._cleanup(db, app, phone)

    def test_returns_existing_patient_by_phone(self, db, app):
        from services.admin_service import find_or_create_patient
        phone = "0999880002"
        with app.app_context():
            p1 = find_or_create_patient("Primero", phone)
            db.session.commit()
            pid = p1.id
            p2 = find_or_create_patient("Segundo", phone)
            db.session.commit()
            assert p2.id == pid
        self._cleanup(db, app, phone)

    def test_increments_total_sessions_on_each_call(self, db, app):
        from services.admin_service import find_or_create_patient
        phone = "0999880003"
        with app.app_context():
            find_or_create_patient("Test", phone)
            db.session.commit()
            p = find_or_create_patient("Test", phone)
            db.session.commit()
            assert p.total_sessions == 2
        self._cleanup(db, app, phone)

    def test_adds_symptom_when_provided(self, db, app):
        from services.admin_service import find_or_create_patient
        phone = "0999880004"
        with app.app_context():
            p = find_or_create_patient("Test", phone, symptom="Ansiedad")
            db.session.commit()
            assert "Ansiedad" in p.symptoms_history
        self._cleanup(db, app, phone)

    def test_no_symptom_leaves_history_empty(self, db, app):
        from services.admin_service import find_or_create_patient
        phone = "0999880005"
        with app.app_context():
            p = find_or_create_patient("Test", phone)
            db.session.commit()
            assert p.symptoms_history == []
        self._cleanup(db, app, phone)

    def test_email_stored_on_create(self, db, app):
        from services.admin_service import find_or_create_patient
        phone = "0999880006"
        with app.app_context():
            p = find_or_create_patient("Test", phone, email="test@example.com")
            db.session.commit()
            assert p.email == "test@example.com"
        self._cleanup(db, app, phone)


# ---------------------------------------------------------------------------
# get_symptom_stats
# ---------------------------------------------------------------------------

class TestGetSymptomStats:
    def test_returns_list(self, db, app):
        from services.admin_service import get_symptom_stats
        with app.app_context():
            result = get_symptom_stats()
            assert isinstance(result, list)

    def test_each_entry_has_required_keys(self, db, app):
        from services.admin_service import get_symptom_stats
        from models import Patient, Appointment
        phone = "0999881001"
        with app.app_context():
            p = Patient(name="Stat Px", phone=phone)
            db.session.add(p)
            db.session.flush()
            a = Appointment(patient_id=p.id, scheduled_at=datetime(2027, 6, 1, 10, 0), symptom="Estrés")
            db.session.add(a)
            db.session.commit()
            stats = get_symptom_stats()
            assert len(stats) > 0
            for entry in stats:
                assert "symptom" in entry
                assert "count" in entry
                assert "pct" in entry
            # cleanup
            db.session.delete(a)
            db.session.delete(p)
            db.session.commit()

    def test_symptom_counted_correctly(self, db, app):
        from services.admin_service import get_symptom_stats
        from models import Patient, Appointment
        phone = "0999881002"
        with app.app_context():
            p = Patient(name="Stat Px 2", phone=phone)
            db.session.add(p)
            db.session.flush()
            for hour in (10, 11, 12):
                a = Appointment(patient_id=p.id, scheduled_at=datetime(2027, 7, 1, hour, 0), symptom="Soledad")
                db.session.add(a)
            db.session.commit()
            stats = get_symptom_stats()
            soledad_entry = next((s for s in stats if s["symptom"] == "Soledad"), None)
            assert soledad_entry is not None
            assert soledad_entry["count"] >= 3
            # cleanup
            from models import Appointment as Appt
            Appt.query.filter_by(patient_id=p.id).delete()
            db.session.delete(p)
            db.session.commit()


# ---------------------------------------------------------------------------
# get_monthly_appointments
# ---------------------------------------------------------------------------

class TestGetMonthlyAppointments:
    def test_returns_list(self, db, app):
        from services.admin_service import get_monthly_appointments
        with app.app_context():
            result = get_monthly_appointments(months=6)
            assert isinstance(result, list)

    def test_each_entry_has_month_and_count(self, db, app):
        from services.admin_service import get_monthly_appointments
        from models import Patient, Appointment
        phone = "0999882001"
        with app.app_context():
            p = Patient(name="Monthly Px", phone=phone)
            db.session.add(p)
            db.session.flush()
            # Appointment in the current month
            now = datetime.now()
            a = Appointment(patient_id=p.id, scheduled_at=now, symptom="Ansiedad", status="confirmed")
            db.session.add(a)
            db.session.commit()
            result = get_monthly_appointments(months=2)
            for entry in result:
                assert "month" in entry
                assert "count" in entry
                assert isinstance(entry["count"], int)
            # cleanup
            db.session.delete(a)
            db.session.delete(p)
            db.session.commit()

    def test_excludes_cancelled_appointments(self, db, app):
        from services.admin_service import get_monthly_appointments
        from models import Patient, Appointment
        phone = "0999882002"
        with app.app_context():
            p = Patient(name="Cancelled Px", phone=phone)
            db.session.add(p)
            db.session.flush()
            a_cancelled = Appointment(
                patient_id=p.id,
                scheduled_at=datetime.now(),
                symptom="Miedo",
                status="cancelled",
            )
            db.session.add(a_cancelled)
            db.session.commit()
            result_before = sum(e["count"] for e in get_monthly_appointments(months=1))

            # confirm it didn't inflate the count
            a_normal = Appointment(
                patient_id=p.id,
                scheduled_at=datetime.now(),
                symptom="Miedo",
                status="pending",
            )
            db.session.add(a_normal)
            db.session.commit()
            result_after = sum(e["count"] for e in get_monthly_appointments(months=1))

            assert result_after == result_before + 1
            # cleanup
            from models import Appointment as Appt
            Appt.query.filter_by(patient_id=p.id).delete()
            db.session.delete(p)
            db.session.commit()
