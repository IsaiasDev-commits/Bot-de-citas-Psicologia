"""Tests for model methods: to_dict(), computed properties, JSON serialization."""
import pytest
from datetime import datetime


class TestPatientModel:
    def test_create_patient(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Ana López", phone="0991234500")
            db.session.add(p)
            db.session.commit()
            assert p.id is not None
            db.session.delete(p)
            db.session.commit()

    def test_to_dict_fields(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Ana López", phone="0991234501", email="ana@test.com")
            db.session.add(p)
            db.session.commit()
            d = p.to_dict()
            assert d["name"] == "Ana López"
            assert d["phone"] == "0991234501"
            assert d["email"] == "ana@test.com"
            assert d["total_sessions"] == 0
            assert d["symptoms_history"] == []
            db.session.delete(p)
            db.session.commit()

    def test_symptoms_history_empty_default(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Test", phone="0991234502")
            db.session.add(p)
            db.session.commit()
            assert p.symptoms_history == []
            db.session.delete(p)
            db.session.commit()

    def test_add_symptom(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Test", phone="0991234503")
            db.session.add(p)
            db.session.commit()
            p.add_symptom("Ansiedad")
            assert "Ansiedad" in p.symptoms_history
            db.session.delete(p)
            db.session.commit()

    def test_add_symptom_no_duplicates(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Test", phone="0991234504")
            db.session.add(p)
            db.session.commit()
            p.add_symptom("Ansiedad")
            p.add_symptom("Ansiedad")
            assert p.symptoms_history.count("Ansiedad") == 1
            db.session.delete(p)
            db.session.commit()

    def test_add_symptom_empty_string_ignored(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Test", phone="0991234505")
            db.session.add(p)
            db.session.commit()
            p.add_symptom("")
            assert p.symptoms_history == []
            db.session.delete(p)
            db.session.commit()

    def test_add_multiple_symptoms(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Test", phone="0991234506")
            db.session.add(p)
            db.session.commit()
            p.add_symptom("Ansiedad")
            p.add_symptom("Tristeza")
            assert len(p.symptoms_history) == 2
            db.session.delete(p)
            db.session.commit()

    def test_to_dict_first_contact_is_iso_string(self, db, app):
        from models import Patient
        with app.app_context():
            p = Patient(name="Test", phone="0991234507")
            db.session.add(p)
            db.session.commit()
            d = p.to_dict()
            if d["first_contact"] is not None:
                datetime.fromisoformat(d["first_contact"])
            db.session.delete(p)
            db.session.commit()

    def test_phone_unique_constraint(self, db, app):
        from models import Patient
        from sqlalchemy.exc import IntegrityError
        with app.app_context():
            p1 = Patient(name="Ana", phone="0991234508")
            db.session.add(p1)
            db.session.commit()
            p2 = Patient(name="Otra", phone="0991234508")
            db.session.add(p2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()
            db.session.delete(p1)
            db.session.commit()


class TestAppointmentModel:
    def _make_patient(self, db, app, phone):
        from models import Patient
        p = Patient(name="Paciente", phone=phone)
        db.session.add(p)
        db.session.flush()
        return p

    def test_status_label_pending(self, db, app):
        from models import Appointment
        with app.app_context():
            p = self._make_patient(db, app, "0992222210")
            a = Appointment(patient_id=p.id, scheduled_at=datetime(2027, 1, 15, 10, 0), status="pending")
            assert a.status_label == "Pendiente"
            db.session.rollback()

    def test_status_label_confirmed(self, db, app):
        from models import Appointment
        with app.app_context():
            p = self._make_patient(db, app, "0992222211")
            a = Appointment(patient_id=p.id, scheduled_at=datetime(2027, 1, 15, 10, 0), status="confirmed")
            assert a.status_label == "Confirmada"
            db.session.rollback()

    def test_status_label_completed(self, db, app):
        from models import Appointment
        with app.app_context():
            p = self._make_patient(db, app, "0992222212")
            a = Appointment(patient_id=p.id, scheduled_at=datetime(2027, 1, 15, 10, 0), status="completed")
            assert a.status_label == "Completada"
            db.session.rollback()

    def test_status_label_cancelled(self, db, app):
        from models import Appointment
        with app.app_context():
            p = self._make_patient(db, app, "0992222213")
            a = Appointment(patient_id=p.id, scheduled_at=datetime(2027, 1, 15, 10, 0), status="cancelled")
            assert a.status_label == "Cancelada"
            db.session.rollback()

    def test_status_label_unknown_falls_back(self, db, app):
        from models import Appointment
        with app.app_context():
            p = self._make_patient(db, app, "0992222216")
            a = Appointment(patient_id=p.id, scheduled_at=datetime(2027, 1, 15, 10, 0), status="unknown_xyz")
            assert a.status_label == "unknown_xyz"
            db.session.rollback()

    def test_to_dict_date_time_format(self, db, app):
        from models import Patient, Appointment
        with app.app_context():
            p = self._make_patient(db, app, "0992222214")
            a = Appointment(
                patient_id=p.id,
                scheduled_at=datetime(2027, 6, 15, 10, 0),
                symptom="Ansiedad",
                status="pending",
            )
            db.session.add(a)
            db.session.commit()
            d = a.to_dict()
            assert d["symptom"] == "Ansiedad"
            assert d["status"] == "pending"
            assert d["status_label"] == "Pendiente"
            assert d["scheduled_date"] == "15/06/2027"
            assert d["scheduled_time"] == "10:00"
            db.session.delete(a)
            db.session.delete(p)
            db.session.commit()

    def test_to_dict_created_at_iso(self, db, app):
        from models import Patient, Appointment
        with app.app_context():
            p = self._make_patient(db, app, "0992222215")
            a = Appointment(patient_id=p.id, scheduled_at=datetime(2027, 1, 15, 10, 0))
            db.session.add(a)
            db.session.commit()
            d = a.to_dict()
            if d["created_at"]:
                datetime.fromisoformat(d["created_at"])
            db.session.delete(a)
            db.session.delete(p)
            db.session.commit()


class TestConversationModel:
    def test_messages_empty_default(self, db, app):
        from models import Conversation
        with app.app_context():
            conv = Conversation()
            db.session.add(conv)
            db.session.commit()
            assert conv.messages == []
            db.session.delete(conv)
            db.session.commit()

    def test_messages_setter_getter(self, db, app):
        from models import Conversation
        with app.app_context():
            conv = Conversation()
            db.session.add(conv)
            db.session.flush()
            msgs = [{"tipo": "user", "mensaje": "Hola"}]
            conv.messages = msgs
            assert conv.messages == msgs
            db.session.rollback()

    def test_detected_symptoms_setter_getter(self, db, app):
        from models import Conversation
        with app.app_context():
            conv = Conversation()
            db.session.add(conv)
            db.session.flush()
            conv.detected_symptoms = ["Ansiedad", "Tristeza"]
            assert "Ansiedad" in conv.detected_symptoms
            db.session.rollback()

    def test_to_dict_message_count(self, db, app):
        from models import Conversation
        with app.app_context():
            conv = Conversation()
            db.session.add(conv)
            db.session.flush()
            conv.messages = [{"tipo": "user"}, {"tipo": "bot"}]
            db.session.commit()
            d = conv.to_dict()
            assert d["message_count"] == 2
            db.session.delete(conv)
            db.session.commit()

    def test_to_dict_fields_present(self, db, app):
        from models import Conversation
        with app.app_context():
            conv = Conversation(session_id="abc123")
            db.session.add(conv)
            db.session.commit()
            d = conv.to_dict()
            assert "id" in d
            assert "messages" in d
            assert "detected_symptoms" in d
            assert d["session_id"] == "abc123"
            db.session.delete(conv)
            db.session.commit()

    def test_malformed_json_returns_empty_list(self, db, app):
        from models import Conversation
        with app.app_context():
            conv = Conversation()
            conv._messages = "not-valid-json"
            conv._detected_symptoms = "{broken"
            assert conv.messages == []
            assert conv.detected_symptoms == []
