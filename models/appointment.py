from datetime import datetime
from . import db


APPOINTMENT_STATUSES = ("pending", "confirmed", "completed", "cancelled")

STATUS_LABELS = {
    "pending": "Pendiente",
    "confirmed": "Confirmada",
    "completed": "Completada",
    "cancelled": "Cancelada",
}


class Appointment(db.Model):
    __tablename__ = "appointments"
    __table_args__ = (
        # Evita doble booking: mismo horario no puede tener dos citas activas
        db.UniqueConstraint(
            "scheduled_at",
            name="uq_appointments_scheduled_at_active",
        ),
        db.Index("ix_appointments_scheduled_at", "scheduled_at"),
        db.Index("ix_appointments_status", "status"),
        db.Index("ix_appointments_patient_id", "patient_id"),
        db.Index("ix_appointments_created_at", "created_at"),
        db.Index("ix_appointments_calendar_event_id", "calendar_event_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    symptom = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")
    calendar_event_id = db.Column(db.String(200), nullable=True)
    psychologist_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "patient_phone": self.patient.phone if self.patient else None,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "scheduled_date": self.scheduled_at.strftime("%d/%m/%Y") if self.scheduled_at else None,
            "scheduled_time": self.scheduled_at.strftime("%H:%M") if self.scheduled_at else None,
            "symptom": self.symptom,
            "status": self.status,
            "status_label": self.status_label,
            "calendar_event_id": self.calendar_event_id,
            "psychologist_notes": self.psychologist_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
