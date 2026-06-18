import os
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

# Cargar .env antes de cualquier os.getenv() — crítico para Sentry y otros servicios
load_dotenv()

from flask import Flask, render_template, request, session, redirect, url_for, jsonify, make_response
from googleapiclient.errors import HttpError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager
from dateutil import parser

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

_sentry_dsn = os.getenv('SENTRY_DSN')
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[FlaskIntegration()],
        traces_sample_rate=0.05,
        environment=os.getenv('FLASK_ENV', 'development'),
        send_default_pii=False,
    )

from services.validation_service import ValidationService
from constants import SINTOMAS_DISPONIBLES
from services.conversation_service import ConversationService
from services.appointment_service import (
    validar_telefono,
    validar_horario_cita,
    verificar_disponibilidad_atomica,
    crear_evento_calendar,
    enviar_correo_confirmacion,
    agendar_cita_completa,
    get_calendar_service,
    parsear_fecha_google
)

app = Flask(__name__)

# ==================== BASE DE DATOS (PostgreSQL) ====================
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///equilibra_dev.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

from models import db, User
from flask_migrate import Migrate
db.init_app(app)
migrate = Migrate(app, db)

# ==================== FLASK-LOGIN ====================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "admin.login"
login_manager.login_message = "Inicia sesión para acceder al panel."

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ==================== BLUEPRINT ADMIN ====================
from admin import admin_bp
app.register_blueprint(admin_bp)

# Blueprint de debug: solo disponible fuera de producción
if os.environ.get('FLASK_ENV') != 'production':
    from debug_routes import debug_bp
    app.register_blueprint(debug_bp)
    app.logger.info("Blueprint de debug registrado (solo entorno de desarrollo)")

# En desarrollo sin migraciones aplicadas, crear tablas automáticamente.
# En producción se usa: flask db upgrade
if os.environ.get('FLASK_ENV') != 'production':
    with app.app_context():
        try:
            db.create_all()
        except Exception:
            pass

# Configuración desde variables de entorno
app.secret_key = os.getenv("FLASK_SECRET_KEY", "clave_por_defecto_para_desarrollo")

app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  

# Configuración para producción en Render
if os.environ.get('FLASK_ENV') == 'production':
    app.config.update(
        DEBUG=False,
        TESTING=False,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax"
    )
else:
    app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

# Usar HTTPS para url_for() en Render
if 'RENDER' in os.environ:
    app.config['PREFERRED_URL_SCHEME'] = 'https'

csrf = CSRFProtect(app)

# Sesiones server-side cuando Redis está disponible (evita límite 4 KB de cookie)
_redis_url = os.getenv('REDIS_URL')
if _redis_url:
    from flask_session import Session
    import redis as _redis_lib
    app.config.update(
        SESSION_TYPE='redis',
        SESSION_REDIS=_redis_lib.from_url(_redis_url),
        SESSION_USE_SIGNER=True,
        SESSION_PERMANENT=False,
        SESSION_KEY_PREFIX='equilibra:session:',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV') == 'production',
    )
    Session(app)

_limiter_storage = _redis_url or 'memory://'

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["2000 per day", "500 per hour"],
    storage_uri=_limiter_storage,
    strategy="fixed-window"
)

# Configuración de logging mejorada para Render
if not os.path.exists('logs'):
    os.makedirs('logs')

handler = RotatingFileHandler('logs/app.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

# También mostrar logs en consola para Render
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
app.logger.addHandler(console_handler)

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

if os.environ.get('FLASK_ENV') != 'production':
    app.logger.debug(f"Python version: {sys.version}")
    app.logger.debug(f"Current directory: {os.getcwd()}")
    app.logger.debug(f"Files in directory: {os.listdir('.')}")

# Crear directorios necesarios
for directory in ["conversaciones", "datos", "logs", "services"]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# ==================== SERVICIOS ====================

validation_service = ValidationService()
@app.route("/", methods=["GET", "POST"])
@limiter.limit("500 per hour")
def index():
    """
    Ruta principal de Equilibra - Versión refactorizada usando ConversationService
    (State Pattern + Service Pattern para mejor arquitectura)
    """
    # Inicializar servicio de conversación
    conversation_service = ConversationService()
    
    # Inicializar sesión si es necesario
    conversation_service.initialize_session()
    
    if request.method == "POST":
        # Manejar solicitud POST usando el servicio de conversación
        success, error_message = conversation_service.handle_post_request(request.form)
        
        if not success and error_message:
            # Si hay un error, renderizar con mensaje de error
            template_data = conversation_service.get_template_data()
            return render_template("index.html", error=error_message, **template_data)
        
        # Redirigir para evitar reenvío de formulario
        return redirect(url_for("index"))
    
    # GET request - simplemente renderizar la plantilla con datos actuales
    template_data = conversation_service.get_template_data()
    return render_template("index.html", **template_data)

@app.route("/reset", methods=["POST"])
@limiter.limit("50 per hour")
def reset():
    try:
        ConversationService().reset_session()
        app.logger.info("Sesión reiniciada por el usuario")
        return jsonify({"status": "success"})
    except Exception as e:
        app.logger.error(f"Error al reiniciar sesión: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cancelar_cita", methods=["POST"])
@limiter.limit("50 per hour")
def cancelar_cita():
    try:
        ConversationService().cancel_appointment_flow()
        return jsonify({"status": "success", "message": "Proceso de cita cancelado"})
    except Exception as e:
        app.logger.error(f"Error al cancelar cita: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/verificar-horario", methods=["POST"])
@limiter.limit("60 per minute")
def verificar_horario():
    try:
        data = request.get_json(silent=True)
        if not data or 'fecha' not in data or 'hora' not in data:
            return jsonify({"error": "Datos incompletos"}), 400
        
        fecha = data['fecha']
        hora = data['hora']
        
        app.logger.info(f"🔍 Verificando horario: {fecha} {hora}")
        
        # Validación básica primero
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
            datetime.strptime(hora, "%H:%M")
        except ValueError:
            return jsonify({"error": "Formato de fecha u hora inválido"}), 400
        
        # Verificar servicio de calendario primero
        service = get_calendar_service()
        if not service:
            app.logger.error("❌ Servicio de calendario no disponible")
            return jsonify({"disponible": False, "error": "Servicio no disponible"})
        
        # Verificación estricta
        start_time = f"{fecha}T{hora}:00-05:00"
        end_time = f"{fecha}T{int(hora.split(':')[0])+1}:00:00-05:00"
        
        time_min = f"{fecha}T00:00:00-05:00"
        time_max = f"{fecha}T23:59:59-05:00"
        
        try:
            eventos = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                maxResults=50,
                orderBy='startTime'
            ).execute()
            
            app.logger.info(f"📅 Eventos encontrados: {len(eventos.get('items', []))}")
            
        except Exception as e:
            app.logger.error(f"❌ Error al listar eventos: {e}")
            return jsonify({"disponible": False, "error": "Error al verificar calendario"})
        
        # Verificar superposición 
        disponible = True
        hora_solicitada_start = parser.isoparse(start_time)
        hora_solicitada_end = parser.isoparse(end_time)
        
        for evento in eventos.get('items', []):
            evento_start_str = evento['start'].get('dateTime', evento['start'].get('date'))
            evento_end_str = evento['end'].get('dateTime', evento['end'].get('date'))
            
            try:
                # Convertir tiempos del evento usando la nueva función
                if 'T' in evento_start_str:
                    fecha_inicio, fecha_fin = parsear_fecha_google(evento)
                    if fecha_inicio and fecha_fin:
                        # Verificar superposición estricta
                        if (fecha_inicio < hora_solicitada_end and fecha_fin > hora_solicitada_start):
                            app.logger.info(f"❌ Horario {hora} ocupado por evento: {evento.get('summary', 'Sin título')}")
                            disponible = False
                            break
                        
            except ValueError as e:
                app.logger.warning(f"Error parsing event time: {e}")
                continue
        
        app.logger.info(f"Horario {fecha} {hora}: {'✅ DISPONIBLE' if disponible else '❌ OCUPADO'}")
        
        return jsonify({"disponible": disponible})
        
    except HttpError as error:
        app.logger.error(f"Error de Google API: {error}")
        return jsonify({"error": "Error de calendario"}), 500
    except Exception as e:
        app.logger.error(f"Error inesperado al verificar horario: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route("/obtener-horarios-disponibles", methods=["POST"])
@limiter.limit("60 per minute")
def obtener_horarios_disponibles():
    """Endpoint para obtener horarios disponibles con validaciones estrictas"""
    try:
        data = request.get_json(silent=True)
        if not data or 'fecha' not in data:
            return jsonify({"error": "Fecha requerida"}), 400
        
        fecha = data['fecha']
        
        # Validar formato de fecha
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido"}), 400
        
        horarios_disponibles = validation_service.get_available_time_slots(fecha)
        
        return jsonify(horarios_disponibles)
        
    except Exception as e:
        app.logger.error(f"Error obteniendo horarios disponibles: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route("/agendar-cita", methods=["POST"])
@limiter.limit("40 per minute")
def agendar_cita():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Datos incompletos"}), 400

        required_fields = ["fecha", "hora", "telefono", "sintoma"]
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Campo requerido: {field}"}), 400
        
        fecha = data["fecha"]
        hora = data["hora"]
        telefono = data["telefono"]
        sintoma = data["sintoma"]

        if sintoma not in SINTOMAS_DISPONIBLES:
            return jsonify({"error": "Síntoma no válido"}), 400

        # Usar la función completa de agendamiento
        success, message, calendar_event_id = agendar_cita_completa(fecha, hora, telefono, sintoma)

        if not success:
            if "inválido" in message.lower() or "formato" in message.lower():
                return jsonify({"error": message}), 400
            elif "no disponible" in message.lower() or "ocupado" in message.lower():
                return jsonify({"error": message}), 409
            else:
                return jsonify({"error": message}), 500

        # Guardar cita y paciente en la base de datos
        try:
            from services.admin_service import find_or_create_patient
            from models import Appointment as AppointmentModel
            patient_name = data.get("nombre", "Paciente")
            patient = find_or_create_patient(
                name=patient_name, phone=telefono, symptom=sintoma
            )
            scheduled_dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
            appt = AppointmentModel(
                patient_id=patient.id,
                scheduled_at=scheduled_dt,
                symptom=sintoma,
                status="pending",
                calendar_event_id=calendar_event_id,  # ID real del evento
            )
            db.session.add(appt)
            db.session.commit()
        except Exception as db_err:
            app.logger.warning(f"No se pudo guardar cita en DB: {db_err}")

        app.logger.info(f"✅ Cita agendada exitosamente: {fecha} {hora} para {telefono}")

        # Actualizar sesión para mostrar estado final
        if "conversacion_data" not in session:
            session["conversacion_data"] = {"interacciones": []}

        mensaje_confirmacion = (
            f"✅ **Cita confirmada**\n\n"
            f"📅 **Fecha:** {fecha}\n"
            f"⏰ **Hora:** {hora}\n"
            f"📱 **Teléfono:** {telefono}\n\n"
            f"Tu cita ha sido registrada correctamente."
        )
        mensaje_cierre = (
            f"💚 **Gracias por agendar con Equilibra**\n\n"
            f"Hemos recibido tu solicitud y nos pondremos en contacto contigo pronto.\n"
            f"Gracias por confiar en este espacio."
        )

        conversacion_data = session["conversacion_data"]
        conversacion_data.setdefault("interacciones", []).extend([
            {"tipo": "bot", "mensaje": mensaje_confirmacion, "sintoma": sintoma,
             "timestamp": datetime.now().isoformat()},
            {"tipo": "bot", "mensaje": mensaje_cierre, "sintoma": sintoma,
             "timestamp": datetime.now().isoformat()},
        ])
        session["estado"] = "fin"
        session["conversacion_data"] = conversacion_data

        return jsonify({
            "status": "success",
            "message": "Cita agendada exitosamente",
        })
        
    except Exception as e:
        app.logger.error(f"Error al agendar cita: {e}")
        return jsonify({"error": "Error al procesar la cita"}), 500

@app.route('/health')
def health_check():
    """
    Health check ligero: verifica configuración de servicios sin hacer llamadas externas.
    Para evitar latencia en monitoreos frecuentes (Render, UptimeRobot, etc.).
    """
    try:
        groq_ok = bool(os.getenv('GROQ_API_KEY'))
        email_ok = bool(os.getenv('RESEND_API_KEY'))
        calendar_ok = bool(os.getenv('GOOGLE_CREDENTIALS'))
        db_ok = False
        try:
            db.session.execute(db.text("SELECT 1"))
            db_ok = True
        except Exception:
            pass

        all_ok = all([groq_ok, email_ok, calendar_ok, db_ok])
        return jsonify({
            'status': 'healthy' if all_ok else 'degraded',
            'services': {
                'groq': groq_ok,
                'email': email_ok,
                'calendar': calendar_ok,
                'database': db_ok,
            },
        }), 200 if all_ok else 503
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# Ruta para sitemap.xml 
@app.route('/sitemap.xml')
def sitemap():
    """Generar sitemap XML correctamente"""
    try:
        url_root = request.url_root.rstrip('/')
        
        # Crear sitemap manualmente sin usar template
        sitemap_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{url_root}/</loc>
        <lastmod>{datetime.now().strftime('%Y-%m-%d')}</lastmod>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>'''
        
        response = make_response(sitemap_xml)
        response.headers["Content-Type"] = "application/xml"
        return response
    except Exception as e:
        app.logger.error(f"Error generando sitemap: {e}")
        return '<?xml version="1.0" encoding="UTF-8"?><error>Error generating sitemap</error>', 500

# Ruta para robots.txt 
@app.route('/robots.txt')
def robots():
    """Generar robots.txt dinámicamente"""
    robots_txt = f"""User-agent: *
Allow: /
Disallow: /admin/
Disallow: /private/
Disallow: /reset
Disallow: /cancelar_cita

Sitemap: {request.url_root.rstrip('/')}/sitemap.xml
"""
    response = make_response(robots_txt)
    response.headers["Content-Type"] = "text/plain"
    return response

@app.after_request
def set_security_headers(response):
    """Agrega headers de seguridad HTTP a todas las respuestas."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # CSP: permite inline scripts/styles (requerido por Tailwind CDN y window.__CSRF_TOKEN__)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    if os.environ.get("FLASK_ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.errorhandler(429)
def ratelimit_handler(e):
    app.logger.warning(f"Límite de tasa excedido: {e}")
    return jsonify({"error": "Demasiadas solicitudes. Por favor, intenta más tarde."}), 429

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Error interno del servidor: {error}")
    return jsonify({"error": "Error interno del servidor"}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint no encontrado"}), 404

# Configuración para producción en Render
if __name__ == "__main__":
    # Crear tablas de la base de datos si no existen
    with app.app_context():
        db.create_all()
        app.logger.info("✅ Tablas de base de datos verificadas/creadas")

    # Verificar variables de entorno en producción
    if os.environ.get('FLASK_ENV') == 'production':
        required_env_vars = ["FLASK_SECRET_KEY", "EMAIL_USER", "EMAIL_PASSWORD", "PSICOLOGO_EMAIL", "GOOGLE_CREDENTIALS", "GROQ_API_KEY"]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing_vars:
            app.logger.error(f"ERROR: Variables de entorno faltantes en producción: {missing_vars}")
            # No salir en producción, solo loggear el error
        else:
            app.logger.info("✅ Todas las variables de entorno requeridas están configuradas")
    
    # Crear directorios necesarios
    for directory in ["logs", "conversaciones", "datos"]:
        if not os.path.exists(directory):
            os.makedirs(directory)
    
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    app.logger.info(f"Iniciando aplicación Equilibra en puerto {port}")
    
    
    if os.environ.get('FLASK_ENV') == 'production':
        from waitress import serve
        serve(app, host='0.0.0.0', port=port)
    else:
        app.run(host='0.0.0.0', port=port, debug=debug)