from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .user import User
from .patient import Patient
from .appointment import Appointment
from .conversation import Conversation
from .clinical_note import ClinicalNote

__all__ = ["db", "User", "Patient", "Appointment", "Conversation", "ClinicalNote"]
