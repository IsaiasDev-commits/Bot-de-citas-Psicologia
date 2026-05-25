import logging
from datetime import datetime
from models import db, Appointment, Patient
from services.appointment_service import get_calendar_service, parsear_fecha_google

logger = logging.getLogger(__name__)


def sync_from_calendar() -> dict:
    """Pull events from Google Calendar and reconcile with DB."""
    service = get_calendar_service()
    if not service:
        return {"ok": False, "error": "No hay servicio de calendario disponible"}

    try:
        now_iso = datetime.utcnow().isoformat() + "Z"
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now_iso,
                maxResults=100,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = result.get("items", [])
        created = 0
        skipped = 0

        for event in events:
            event_id = event.get("id")
            if Appointment.query.filter_by(calendar_event_id=event_id).first():
                skipped += 1
                continue

            summary = event.get("summary", "")
            description = event.get("description", "")
            start_raw = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
            if not start_raw:
                continue

            scheduled_at = parsear_fecha_google(start_raw)
            if not scheduled_at:
                continue

            phone = _extract_phone(description)
            patient_name = _extract_patient_name(summary)
            symptom = _extract_symptom(description)

            patient = Patient.query.filter_by(phone=phone).first() if phone else None
            if not patient and patient_name:
                patient = Patient(name=patient_name, phone=phone or "desconocido")
                db.session.add(patient)
                db.session.flush()

            if patient:
                appt = Appointment(
                    patient_id=patient.id,
                    scheduled_at=scheduled_at,
                    symptom=symptom,
                    status="pending",
                    calendar_event_id=event_id,
                )
                db.session.add(appt)
                created += 1

        db.session.commit()
        return {"ok": True, "created": created, "skipped": skipped}

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en sync_from_calendar: {e}")
        return {"ok": False, "error": str(e)}


def update_calendar_event_status(appointment: Appointment, new_status: str) -> bool:
    """Update or delete a Google Calendar event when admin changes appointment status."""
    if not appointment.calendar_event_id:
        return True

    service = get_calendar_service()
    if not service:
        return False

    try:
        event = service.events().get(calendarId="primary", eventId=appointment.calendar_event_id).execute()

        if new_status == "cancelled":
            service.events().delete(calendarId="primary", eventId=appointment.calendar_event_id).execute()
            return True

        status_emojis = {"confirmed": "✅ CONFIRMADA", "completed": "✔️ COMPLETADA", "pending": "⏳ PENDIENTE"}
        label = status_emojis.get(new_status, new_status.upper())

        desc = event.get("description", "")
        for emoji in ["✅", "✔️", "⏳"]:
            desc = desc.replace(emoji, "")
        desc = f"{label}\n{desc.strip()}"

        event["description"] = desc
        service.events().update(calendarId="primary", eventId=appointment.calendar_event_id, body=event).execute()
        return True

    except Exception as e:
        logger.error(f"Error actualizando evento de calendario: {e}")
        return False


def _extract_phone(text: str) -> str:
    import re
    match = re.search(r"\b0[0-9]{9}\b", text or "")
    return match.group(0) if match else ""


def _extract_patient_name(summary: str) -> str:
    parts = (summary or "").split("-")
    if len(parts) >= 2:
        return parts[-1].strip()
    return summary.strip()


def _extract_symptom(description: str) -> str:
    for line in (description or "").splitlines():
        if "síntoma" in line.lower() or "motivo" in line.lower():
            parts = line.split(":", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return ""
