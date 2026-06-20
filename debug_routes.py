"""
Blueprint de rutas de diagnóstico - solo se registra fuera de producción.
NUNCA debe estar accesible en producción.
"""

from flask import Blueprint, jsonify
import os

debug_bp = Blueprint("debug", __name__)


@debug_bp.route("/debug-env")
def debug_env():
    return jsonify({
        "GOOGLE_CREDENTIALS_SET": bool(os.getenv("GOOGLE_CREDENTIALS")),
        "GOOGLE_CREDENTIALS_LENGTH": len(os.getenv("GOOGLE_CREDENTIALS", "")),
        "GROQ_API_KEY_SET": bool(os.getenv("GROQ_API_KEY")),
        "EMAIL_USER_SET": bool(os.getenv("EMAIL_USER")),
        "FLASK_ENV": os.getenv("FLASK_ENV"),
        "RENDER": os.getenv("RENDER"),
        "PORT": os.getenv("PORT"),
        "FLASK_SECRET_KEY_SET": bool(os.getenv("FLASK_SECRET_KEY")),
        "RESEND_API_KEY_SET": bool(os.getenv("RESEND_API_KEY")),
        "PSICOLOGO_EMAIL_SET": bool(os.getenv("PSICOLOGO_EMAIL")),
    })


@debug_bp.route("/debug-env-detailed")
def debug_env_detailed():
    safe = {}
    for key, value in os.environ.items():
        if any(w in key.upper() for w in ("KEY", "SECRET", "PASSWORD", "CREDENTIALS", "TOKEN")):
            safe[key] = "***" + value[-4:] if len(value) > 4 else "***"
        else:
            safe[key] = value
    return jsonify({"total_variables": len(safe), "variables": safe})


@debug_bp.route("/test-calendar-connection")
def test_calendar_connection():
    from services.appointment_service import get_calendar_service
    from googleapiclient.errors import HttpError
    try:
        service = get_calendar_service()
        if not service:
            return jsonify({"error": "No se pudo crear el servicio"})
        calendars = service.calendarList().list().execute()
        test_event = {
            "summary": "Test Connection - DELETE",
            "start": {"dateTime": "2025-01-01T10:00:00-05:00", "timeZone": "America/Guayaquil"},
            "end": {"dateTime": "2025-01-01T11:00:00-05:00", "timeZone": "America/Guayaquil"},
        }
        created = service.events().insert(calendarId="primary", body=test_event).execute()
        service.events().delete(calendarId="primary", eventId=created["id"]).execute()
        return jsonify({
            "status": "success",
            "calendars": len(calendars.get("items", [])),
            "message": "Conexión exitosa con Google Calendar",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_bp.route("/debug-calendario")
def debug_calendario():
    from services.appointment_service import get_calendar_service
    from datetime import datetime, timedelta
    try:
        service = get_calendar_service()
        if not service:
            return jsonify({"error": "No hay servicio de calendario"})
        hoy = datetime.now().strftime("%Y-%m-%dT00:00:00-05:00")
        manana = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT00:00:00-05:00")
        eventos = service.events().list(
            calendarId="primary", timeMin=hoy, timeMax=manana,
            singleEvents=True, maxResults=50, orderBy="startTime",
        ).execute()
        return jsonify({
            "total_eventos": len(eventos.get("items", [])),
            "eventos": [
                {"summary": e.get("summary"), "start": e["start"], "end": e["end"], "id": e.get("id")}
                for e in eventos.get("items", [])
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@debug_bp.route("/test-calendar")
def test_calendar():
    from services.appointment_service import get_calendar_service
    from googleapiclient.errors import HttpError
    try:
        service = get_calendar_service()
        if not service:
            return jsonify({"error": "No se pudo crear el servicio"})
        calendars = service.calendarList().list().execute()
        test_event = {
            "summary": "Test Equilibra - Borrar",
            "start": {"dateTime": "2025-01-01T10:00:00-05:00", "timeZone": "America/Guayaquil"},
            "end": {"dateTime": "2025-01-01T11:00:00-05:00", "timeZone": "America/Guayaquil"},
        }
        created = service.events().insert(calendarId="primary", body=test_event).execute()
        service.events().delete(calendarId="primary", eventId=created["id"]).execute()
        return jsonify({
            "status": "success",
            "calendars": [c["summary"] for c in calendars.get("items", [])],
            "message": "Conexión exitosa con Google Calendar - Permisos de lectura/escritura confirmados",
        })
    except HttpError as e:
        if e.resp.status == 403:
            return jsonify({"error": "Error 403: Permisos insuficientes."})
        return jsonify({"error": f"Error de Google Calendar: {e}"})
    except Exception as e:
        return jsonify({"error": str(e)})

