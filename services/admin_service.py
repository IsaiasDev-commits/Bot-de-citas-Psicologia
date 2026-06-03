from datetime import datetime, timedelta
from collections import Counter
from sqlalchemy import desc
from models import db, Patient, Appointment, Conversation, ClinicalNote, User


def get_dashboard_stats() -> dict:
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = today_start + timedelta(days=1)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    total_patients = Patient.query.count()
    new_today = Patient.query.filter(Patient.first_contact >= today_start).count()

    today_appointments = Appointment.query.filter(
        Appointment.scheduled_at >= today_start,
        Appointment.scheduled_at < today_end,
        Appointment.status != "cancelled",
    ).count()

    pending_count = Appointment.query.filter_by(status="pending").count()

    week_appointments = Appointment.query.filter(
        Appointment.scheduled_at >= week_start,
        Appointment.status != "cancelled",
    ).count()

    all_symptoms = [a.symptom for a in Appointment.query.with_entities(Appointment.symptom).all() if a.symptom]
    top_symptom = Counter(all_symptoms).most_common(1)
    top_symptom = top_symptom[0][0] if top_symptom else "—"

    recurring = Patient.query.filter(Patient.total_sessions >= 2).count()

    return {
        "total_patients": total_patients,
        "new_today": new_today,
        "today_appointments": today_appointments,
        "pending_count": pending_count,
        "week_appointments": week_appointments,
        "top_symptom": top_symptom,
        "recurring_patients": recurring,
    }


def get_today_appointments() -> list:
    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=1)

    appts = (
        Appointment.query
        .filter(Appointment.scheduled_at >= start, Appointment.scheduled_at < end)
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    return appts


def get_recent_appointments(limit: int = 5) -> list:
    since = datetime.utcnow() - timedelta(hours=24)
    return (
        Appointment.query
        .filter(Appointment.created_at >= since)
        .order_by(desc(Appointment.created_at))
        .limit(limit)
        .all()
    )


def get_appointments_paginated(page: int, per_page: int, status: str = None,
                               symptom: str = None, search: str = None,
                               date_from: str = None, date_to: str = None) -> object:
    q = Appointment.query.join(Patient)

    if status:
        q = q.filter(Appointment.status == status)
    if symptom:
        q = q.filter(Appointment.symptom == symptom)
    if search:
        q = q.filter(Patient.name.ilike(f"%{search}%") | Patient.phone.ilike(f"%{search}%"))
    if date_from:
        try:
            q = q.filter(Appointment.scheduled_at >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(Appointment.scheduled_at < end)
        except ValueError:
            pass

    return q.order_by(desc(Appointment.scheduled_at)).paginate(page=page, per_page=per_page, error_out=False)


def get_patients_paginated(page: int, per_page: int, search: str = None) -> object:
    q = Patient.query
    if search:
        q = q.filter(Patient.name.ilike(f"%{search}%") | Patient.phone.ilike(f"%{search}%"))
    return q.order_by(desc(Patient.last_contact)).paginate(page=page, per_page=per_page, error_out=False)


def get_patient_detail(patient_id: int) -> dict:
    patient = Patient.query.get_or_404(patient_id)
    appointments = (
        Appointment.query.filter_by(patient_id=patient_id)
        .order_by(desc(Appointment.scheduled_at))
        .all()
    )
    conversations = (
        Conversation.query.filter_by(patient_id=patient_id)
        .order_by(desc(Conversation.started_at))
        .all()
    )
    clinical_notes = (
        ClinicalNote.query.filter_by(patient_id=patient_id)
        .order_by(desc(ClinicalNote.created_at))
        .all()
    )
    return {
        "patient": patient,
        "appointments": appointments,
        "conversations": conversations,
        "clinical_notes": clinical_notes,
    }


def get_symptom_stats() -> list:
    all_symptoms = [a.symptom for a in Appointment.query.with_entities(Appointment.symptom).all() if a.symptom]
    counter = Counter(all_symptoms)
    total = sum(counter.values()) or 1
    return [
        {"symptom": s, "count": c, "pct": round(c / total * 100)}
        for s, c in counter.most_common(10)
    ]


def get_monthly_appointments(months: int = 6) -> list:
    """Agrupación mensual compatible con PostgreSQL y SQLite."""
    since = datetime.utcnow() - timedelta(days=30 * months)
    appts = (
        Appointment.query
        .with_entities(Appointment.scheduled_at)
        .filter(Appointment.scheduled_at >= since, Appointment.status != "cancelled")
        .all()
    )
    counts: dict = {}
    for (dt,) in appts:
        key = dt.strftime("%Y-%m")
        counts[key] = counts.get(key, 0) + 1

    return [
        {"month": datetime.strptime(k, "%Y-%m").strftime("%b %Y"), "count": v}
        for k, v in sorted(counts.items())
    ]


def get_calendar_appointments(year: int, month: int) -> list:
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    start = datetime(year, month, 1)
    end = datetime(year, month, last_day, 23, 59, 59)

    appts = (
        Appointment.query
        .join(Patient)
        .filter(Appointment.scheduled_at >= start, Appointment.scheduled_at <= end, Appointment.status != "cancelled")
        .order_by(Appointment.scheduled_at.asc())
        .all()
    )
    return appts


def find_or_create_patient(name: str, phone: str, email: str = None, symptom: str = None) -> Patient:
    patient = Patient.query.filter_by(phone=phone).first()
    if not patient:
        patient = Patient(name=name, phone=phone, email=email)
        db.session.add(patient)

    patient.last_contact = datetime.utcnow()
    patient.total_sessions = (patient.total_sessions or 0) + 1
    if symptom:
        patient.add_symptom(symptom)

    db.session.flush()
    return patient
