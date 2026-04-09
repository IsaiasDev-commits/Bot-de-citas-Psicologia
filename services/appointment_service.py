"""
Servicio de agendamiento de citas - Lógica compartida entre app.py y conversation_service.py
"""

import os
import json
import logging
from datetime import datetime
from typing import Tuple, Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dateutil import parser
import resend

logger = logging.getLogger(__name__)

# Importar servicios compartidos
from .validation_service import ValidationService

validation_service = ValidationService()

# ==================== FUNCIONES DE VALIDACIÓN ====================

def validar_telefono(telefono: str) -> Tuple[bool, str]:
    """Validar teléfono usando el servicio de validación"""
    return validation_service.validate_phone(telefono)

def validar_horario_cita(fecha_str: str, hora_str: str) -> Tuple[bool, str]:
    """Validación estricta de horarios de cita"""
    return validation_service.validate_appointment_time(fecha_str, hora_str)

# ==================== GOOGLE CALENDAR ====================

def get_calendar_service():
    """Obtener servicio de Google Calendar"""
    try:
        google_credentials = os.getenv('GOOGLE_CREDENTIALS')
        if not google_credentials:
            logger.error("❌ GOOGLE_CREDENTIALS no configuradas")
            return None
        
        # Limpiar y verificar credenciales
        google_credentials = google_credentials.strip()
        logger.info(f"Longitud de credenciales: {len(google_credentials)}")
        
        try:
            creds_dict = json.loads(google_credentials)
            logger.info("✅ Credenciales JSON parseadas correctamente")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error parseando JSON: {e}")
            logger.error(f"Primeros 100 caracteres: {google_credentials[:100]}")
            return None
            
        # Verificar campos requeridos
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in creds_dict]
        
        if missing_fields:
            logger.error(f"❌ Campos faltantes: {missing_fields}")
            return None
        
        # Crear credenciales
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        logger.info("✅ Servicio de calendario creado exitosamente")
        return service
        
    except Exception as e:
        logger.error(f"❌ Error al obtener servicio de calendario: {e}")
        return None

def crear_evento_calendar(fecha: str, hora: str, telefono: str, sintoma: str) -> Optional[str]:
    """Crear evento en Google Calendar"""
    try:
        # Validar fecha y hora
        datetime.strptime(fecha, "%Y-%m-%d")
        datetime.strptime(hora, "%H:%M")
        
        service = get_calendar_service()
        if not service:
            logger.error("No se pudo obtener el servicio de calendario")
            return None
            
        # Crear el evento con este formato 
        start_time = f"{fecha}T{hora}:00-05:00"
        end_time = f"{fecha}T{int(hora.split(':')[0])+1}:00:00-05:00"
        
        event = {
            'summary': f'Cita Psicológica - {sintoma}',
            'description': f'Teléfono del paciente: {telefono}\nSíntoma principal: {sintoma}\nCita agendada a través de Equilibra',
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/Guayaquil',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/Guayaquil',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 día antes
                    {'method': 'popup', 'minutes': 30},       # 30 minutos antes
                ],
            },
        }
        
        logger.info(f"Intentando crear evento: {fecha} {hora} para {telefono}")
        
        # Intentar crear el evento
        event_created = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
        
        evento_url = event_created.get('htmlLink')
        logger.info(f"✅ Evento creado exitosamente: {evento_url}")
        
        return evento_url
        
    except ValueError as ve:
        logger.error(f"❌ Formato de fecha/hora inválido: {ve}")
        return None
    except HttpError as error:
        logger.error(f"❌ Error de Google Calendar API: {error}")
        # Mostrar más detalles del error
        if error.resp.status == 403:
            logger.error("❌ Error 403: Permisos insuficientes. Verifica que la cuenta de servicio tenga permisos de escritura.")
        elif error.resp.status == 404:
            logger.error("❌ Error 404: Calendario no encontrado.")
        return None
    except Exception as e:
        logger.error(f"❌ Error inesperado al crear evento: {e}")
        return None

def parsear_fecha_google(event: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Parsear fechas de Google Calendar usando dateutil.parser"""
    try:
        fecha_inicio = parser.isoparse(event["start"]["dateTime"])
        fecha_fin = parser.isoparse(event["end"]["dateTime"])
        return fecha_inicio, fecha_fin
    except Exception as e:
        logger.error(f"Error parseando fecha de Google Calendar: {e}")
        return None, None

def verificar_disponibilidad_atomica(fecha: str, hora: str) -> Dict[str, Any]:
    """Verificación atómica estricta con todas las validaciones"""
    try:
        # 1. Validación básica de formato
        datetime.strptime(fecha, "%Y-%m-%d")
        datetime.strptime(hora, "%H:%M")
        
        # 2. Validación estricta de horario
        es_valido, mensaje = validar_horario_cita(fecha, hora)
        if not es_valido:
            logger.warning(f"❌ Validación fallida para {fecha} {hora}: {mensaje}")
            return {"disponible": False, "error": mensaje}
        
        # 3. Verificar disponibilidad en Google Calendar
        service = get_calendar_service()
        if not service:
            return {"disponible": False, "error": "Servicio no disponible"}
            
        start_time = f"{fecha}T{hora}:00-05:00"
        end_time = f"{fecha}T{int(hora.split(':')[0])+1}:00:00-05:00"
        
        # Verificación estricta de eventos
        time_min = f"{fecha}T00:00:00-05:00"
        time_max = f"{fecha}T23:59:59-05:00"
        
        eventos = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            maxResults=50,
            orderBy='startTime'
        ).execute()
        
        hora_solicitada_start = parser.isoparse(start_time)
        hora_solicitada_end = parser.isoparse(end_time)
        
        for evento in eventos.get('items', []):
            evento_start_str = evento['start'].get('dateTime', evento['start'].get('date'))
            evento_end_str = evento['end'].get('dateTime', evento['end'].get('date'))
            
            if 'T' in evento_start_str:
                try:
                    # Usar la nueva función de parseo
                    fecha_inicio, fecha_fin = parsear_fecha_google(evento)
                    if fecha_inicio and fecha_fin:
                        if (fecha_inicio < hora_solicitada_end and fecha_fin > hora_solicitada_start):
                            logger.warning(f"❌ Verificación atómica: Horario {hora} ocupado por {evento.get('summary', 'Sin título')}")
                            return {"disponible": False, "error": "Horario ya ocupado"}
                except ValueError:
                    continue
        
        logger.info(f"✅ Horario {fecha} {hora} disponible y válido")
        return {"disponible": True}
        
    except Exception as e:
        logger.error(f"Error en verificación atómica: {e}")
        return {"disponible": False, "error": str(e)}

# ==================== RESEND EMAIL ====================

def enviar_correo_resend(destinatario: str, fecha: str, hora: str, telefono: str, sintoma: str) -> bool:
    """Usar Resend API para enviar emails"""
    destinatario = "chatbotequilibra@gmail.com"
    try:
        resend_api_key = os.getenv('RESEND_API_KEY')
        
        if not resend_api_key:
            logger.warning("Credenciales de Resend no configuradas")
            return False
            
        # Configurar la API key de Resend
        resend.api_key = resend_api_key
        
        mensaje = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #4CAF82; text-align: center;">📅 NUEVA CITA AGENDADA - EQUILIBRA</h2>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <p><strong>Fecha:</strong> {fecha}</p>
                <p><strong>Hora:</strong> {hora}</p>
                <p><strong>Teléfono:</strong> {telefono}</p>
                <p><strong>Síntoma principal:</strong> {sintoma}</p>
            </div>
            
            <p>La cita ha sido registrada exitosamente en el calendario de Google.</p>
            <p>Por favor contacta al paciente para confirmar los detalles.</p>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 2px solid #4CAF82;">
                <p>Saludos,<br>
                <strong>Equilibra</strong> - Sistema de Citas Psicológicas</p>
            </div>
        </div>
        """
        
        # Enviar el email
        respuesta = resend.Emails.send({
            "from": "Equilibra <onboarding@resend.dev>",
            "to": destinatario,
            "subject": f"✅ Nueva cita agendada - {fecha} {hora}",
            "html": mensaje
        })

        logger.info(f"✅ Correo enviado correctamente via Resend: {respuesta}")
        return True
            
    except Exception as e:
        logger.error(f"❌ Error enviando correo con Resend: {e}")
        return False

def enviar_correo_confirmacion(destinatario: str, fecha: str, hora: str, telefono: str, sintoma: str) -> bool:
    """Versión para Resend que funciona en Render"""
    destinatario = "chatbotequilibra@gmail.com"
    try:
        resend_api_key = os.getenv('RESEND_API_KEY')
        
        if resend_api_key:
            # Usar Resend API
            return enviar_correo_resend(destinatario, fecha, hora, telefono, sintoma)
        else:
            # Fallback: solo loggear 
            logger.info(f"📧 Simulando envío de email a {destinatario}")
            logger.info(f"   Cita: {fecha} {hora} - Tel: {telefono} - Síntoma: {sintoma}")
            return True
            
    except Exception as e:
        logger.warning(f"⚠️ Email no enviado (pero no crítico): {e}")
        return True

# ==================== AGENDAMIENTO COMPLETO ====================

def agendar_cita_completa(fecha: str, hora: str, telefono: str, sintoma: str) -> Tuple[bool, str, Optional[str]]:
    """
    Función principal para agendar una cita completa
    Returns: (success, message, evento_url)
    """
    try:
        # 1. Validar teléfono
        valido, mensaje_error = validar_telefono(telefono)
        if not valido:
            logger.error(f"Teléfono inválido: {mensaje_error}")
            return False, mensaje_error, None
        
        # 2. Validación estricta de horario
        es_valido, mensaje_validacion = validar_horario_cita(fecha, hora)
        if not es_valido:
            logger.error(f"Horario inválido: {mensaje_validacion}")
            return False, mensaje_validacion, None
        
        # 3. Verificación atómica estricta de disponibilidad
        verificacion = verificar_disponibilidad_atomica(fecha, hora)
        if not verificacion.get("disponible", False):
            error_msg = verificacion.get("error", "El horario ya no está disponible")
            logger.error(f"Horario no disponible: {error_msg}")
            return False, error_msg, None
        
        # 4. Crear evento en Google Calendar
        evento_url = crear_evento_calendar(fecha, hora, telefono, sintoma)
        if not evento_url:
            logger.error("Error al crear evento en Google Calendar")
            return False, "Error al crear la cita en el calendario", None
        
        # 5. Enviar correo de confirmación (no bloqueante)
        email_enviado = enviar_correo_confirmacion(
            "chatbotequilibra@gmail.com",
            fecha,
            hora,
            telefono,
            sintoma
        )
        
        if not email_enviado:
            logger.warning("⚠️ Email no enviado (pero cita creada en calendario)")
            # No fallar si el email no se envía, solo loggear warning
        
        logger.info(f"✅ Cita agendada exitosamente: {fecha} {hora} para {telefono}")
        return True, "Cita agendada exitosamente", evento_url
        
    except Exception as e:
        logger.error(f"Error al agendar cita: {e}")
        return False, str(e), None