from datetime import datetime
import json
from . import db


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(150), nullable=True)
    first_contact = db.Column(db.DateTime, default=datetime.utcnow)
    last_contact = db.Column(db.DateTime, default=datetime.utcnow)
    total_sessions = db.Column(db.Integer, default=0)
    _symptoms_history = db.Column("symptoms_history", db.Text, default="[]")

    appointments = db.relationship("Appointment", backref="patient", lazy="dynamic", cascade="all, delete-orphan")
    conversations = db.relationship("Conversation", backref="patient", lazy="dynamic", cascade="all, delete-orphan")
    clinical_notes = db.relationship("ClinicalNote", backref="patient", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def symptoms_history(self) -> list:
        try:
            return json.loads(self._symptoms_history or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @symptoms_history.setter
    def symptoms_history(self, value: list):
        self._symptoms_history = json.dumps(value, ensure_ascii=False)

    def add_symptom(self, symptom: str):
        history = self.symptoms_history
        if symptom and symptom not in history:
            history.append(symptom)
            self.symptoms_history = history

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "first_contact": self.first_contact.isoformat() if self.first_contact else None,
            "last_contact": self.last_contact.isoformat() if self.last_contact else None,
            "total_sessions": self.total_sessions,
            "symptoms_history": self.symptoms_history,
        }
