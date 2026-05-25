from datetime import datetime, timedelta
from flask import request, jsonify
from flask_login import current_user
from models import db, Appointment, Patient, ClinicalNote
from services.calendar_sync_service import update_calendar_event_status, sync_from_calendar
from .decorators import login_required_admin
from . import admin_bp


@admin_bp.route("/api/appointments/<int:appt_id>/status", methods=["PATCH"])
@login_required_admin
def update_appointment_status(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")

    allowed = ("pending", "confirmed", "completed", "cancelled")
    if new_status not in allowed:
        return jsonify({"error": f"Estado inválido. Permitidos: {allowed}"}), 400

    cal_ok = update_calendar_event_status(appt, new_status)
    appt.status = new_status
    appt.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "ok": True,
        "status": appt.status,
        "status_label": appt.status_label,
        "calendar_updated": cal_ok,
    })


@admin_bp.route("/api/patients/<int:patient_id>/notes", methods=["POST"])
@login_required_admin
def add_clinical_note(patient_id):
    Patient.query.get_or_404(patient_id)
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()

    if not content:
        return jsonify({"error": "El contenido no puede estar vacío"}), 400

    note = ClinicalNote(
        patient_id=patient_id,
        author_id=current_user.id,
        content=content,
        is_private=data.get("is_private", True),
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({"ok": True, "note": note.to_dict()}), 201


@admin_bp.route("/api/patients/<int:patient_id>/notes/<int:note_id>", methods=["PUT"])
@login_required_admin
def update_clinical_note(patient_id, note_id):
    note = ClinicalNote.query.filter_by(id=note_id, patient_id=patient_id).first_or_404()
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()

    if not content:
        return jsonify({"error": "El contenido no puede estar vacío"}), 400

    note.content = content
    note.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "note": note.to_dict()})


@admin_bp.route("/api/patients/<int:patient_id>/notes/<int:note_id>", methods=["DELETE"])
@login_required_admin
def delete_clinical_note(patient_id, note_id):
    note = ClinicalNote.query.filter_by(id=note_id, patient_id=patient_id).first_or_404()
    db.session.delete(note)
    db.session.commit()
    return jsonify({"ok": True})


@admin_bp.route("/api/calendar/sync", methods=["POST"])
@login_required_admin
def calendar_sync():
    result = sync_from_calendar()
    return jsonify(result)


@admin_bp.route("/api/appointments/check-new")
@login_required_admin
def check_new_appointments():
    since = datetime.utcnow() - timedelta(hours=24)
    appts = (
        Appointment.query
        .join(Patient)
        .filter(Appointment.created_at >= since, Appointment.status == "pending")
        .order_by(Appointment.created_at.desc())
        .limit(10)
        .all()
    )
    return jsonify({
        "count": len(appts),
        "appointments": [a.to_dict() for a in appts],
    })


@admin_bp.route("/api/appointments/<int:appt_id>/notes", methods=["PATCH"])
@login_required_admin
def update_appointment_notes(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    data = request.get_json(silent=True) or {}
    appt.psychologist_notes = (data.get("notes") or "").strip()
    appt.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})
