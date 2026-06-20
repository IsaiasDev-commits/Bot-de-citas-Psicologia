import json
from constants import utcnow
from . import db


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=True)
    session_id = db.Column(db.String(200), nullable=True)
    _messages = db.Column("messages", db.Text, default="[]")
    _detected_symptoms = db.Column("detected_symptoms", db.Text, default="[]")
    started_at = db.Column(db.DateTime, default=utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)

    @property
    def messages(self) -> list:
        try:
            return json.loads(self._messages or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @messages.setter
    def messages(self, value: list):
        self._messages = json.dumps(value, ensure_ascii=False)

    @property
    def detected_symptoms(self) -> list:
        try:
            return json.loads(self._detected_symptoms or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @detected_symptoms.setter
    def detected_symptoms(self, value: list):
        self._detected_symptoms = json.dumps(value, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "session_id": self.session_id,
            "messages": self.messages,
            "detected_symptoms": self.detected_symptoms,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "message_count": len(self.messages),
        }
