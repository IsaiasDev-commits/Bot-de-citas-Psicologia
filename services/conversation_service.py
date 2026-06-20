"""
Servicio de conversación para manejar la lógica del flujo de conversación en Equilibra.
Implementa State Pattern para manejar los diferentes estados del flujo de conversación.
"""

from datetime import datetime, timedelta
import logging
from typing import Dict, Any, Optional, Tuple
from flask import session, request
from models import db as _db, Conversation as _ConvModel, Patient as _Patient
from .ai_service import AIServiceFactory
from .appointment_service import agendar_cita_completa as _agendar_cita_completa
from .validation_service import ValidationService
from constants import SINTOMAS_DISPONIBLES, detectar_crisis, CRISIS_RESPONSE, utcnow

logger = logging.getLogger(__name__)


class ConversationState:
    """Clase base para estados de conversación (State Pattern)"""
    
    def __init__(self, conversation_service):
        self.conversation_service = conversation_service
    
    def handle_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Maneja una solicitud en este estado"""
        raise NotImplementedError
    
    def get_template_data(self) -> Dict[str, Any]:
        """Obtiene datos para renderizar la plantilla"""
        return {}


class InitialState(ConversationState):
    """Estado inicial - selección de síntomas"""
    
    def handle_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        sintomas = request_data.get('sintomas', [])
        
        if not sintomas:
            return False, "Por favor selecciona un síntoma"
        
        session["sintoma_actual"] = sintomas[0]
        session["estado"] = "evaluacion"
        
        # Agregar interacción al historial
        self.conversation_service.add_bot_interaction(
            f"Entiendo que estás experimentando {sintomas[0].lower()}. ¿Desde cuándo lo notas?",
            sintomas[0]
        )
        
        logger.info(f"Usuario seleccionó síntoma: {sintomas[0]}")
        return True, None


class EvaluationState(ConversationState):
    """Estado de evaluación - fecha de inicio del síntoma"""
    
    def handle_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        fecha = request_data.get('fecha_inicio_sintoma')
        
        if not fecha:
            return False, "Por favor ingresa la fecha de inicio del síntoma"
        
        duracion = self.conversation_service.calculate_duration_days(fecha)
        session["estado"] = "profundizacion"
        
        # Determinar comentario basado en duración
        if duracion < 30:
            comentario = "Es bueno que lo identifiques temprano."
        elif duracion < 365:
            comentario = "Varios meses con esto... debe ser difícil."
        else:
            comentario = "Tu perseverancia es admirable."
        
        # Obtener respuesta del sistema conversacional
        respuesta = self.conversation_service.get_conversation_response("")
        self.conversation_service.add_bot_interaction(
            f"{comentario} {respuesta}",
            session.get("sintoma_actual")
        )
        
        return True, None


_MAX_USER_INPUT = 2000  # caracteres máximos por mensaje de usuario


class DeepeningState(ConversationState):
    """Estado de profundización - conversación normal"""

    def handle_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        user_input = request_data.get('user_input', '').strip()[:_MAX_USER_INPUT]
        solicitar_cita = request_data.get('solicitar_cita')
        
        # Si el usuario presiona explícitamente el botón de solicitar cita
        if solicitar_cita and solicitar_cita.lower() == "true":
            session["estado"] = "agendar_cita"
            self.conversation_service.add_user_interaction("Quiero agendar una cita")
            
            mensaje = (
                "Excelente decisión. Por favor completa los datos para tu cita presencial:\n\n"
                "Selecciona una fecha disponible\n"
                "Elige un horario que te convenga\n"
                "Ingresa tu numero de telefono para contactarte"
            )
            self.conversation_service.add_bot_interaction(mensaje, session.get("sintoma_actual"))
            logger.info("Usuario solicitó cita mediante botón - Saltando a agendamiento")
            return True, None
        
        # Conversación normal
        if user_input:
            self.conversation_service.add_user_interaction(user_input)
            respuesta = self.conversation_service.get_conversation_response(user_input)
            self.conversation_service.add_bot_interaction(respuesta, session.get("sintoma_actual"))
        
        return True, None


class AppointmentState(ConversationState):
    """Estado de agendamiento de cita"""
    
    def __init__(self, conversation_service):
        super().__init__(conversation_service)
        self.validation_service = ValidationService()
    
    def handle_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        cancelar_cita = request_data.get('cancelar_cita')
        
        if cancelar_cita:
            session["estado"] = "profundizacion"
            self.conversation_service.add_bot_interaction(
                "Entendido, no hay problema. ¿Hay algo más en lo que pueda ayudarte hoy?",
                session.get("sintoma_actual")
            )
            logger.info("Usuario canceló proceso de cita")
            return True, None
        
        # Procesar datos de cita
        fecha = request_data.get('fecha_cita')
        telefono = request_data.get('telefono', '').strip()
        hora = request_data.get('hora_seleccionada')
        
        if not all([fecha, telefono, hora]):
            self.conversation_service.add_bot_interaction(
                "Campos incompletos. Por favor completa todos los datos requeridos para agendar tu cita.",
                None
            )
            logger.warning("Faltan campos en el formulario de cita")
            return False, "Campos incompletos"
        
        # Validar teléfono
        valido, mensaje_error = self.validation_service.validate_phone(telefono)
        if not valido:
            self.conversation_service.add_bot_interaction(
                f"{mensaje_error}. Por favor, ingrésalo de nuevo.",
                None
            )
            logger.warning(f"Teléfono inválido: {telefono}")
            return False, mensaje_error
        
        # Validar horario
        es_valido, mensaje_validacion = self.validation_service.validate_appointment_time(fecha, hora)
        if not es_valido:
            self.conversation_service.add_bot_interaction(
                f"{mensaje_validacion}. Por favor selecciona otro horario.",
                None
            )
            logger.warning(f"Horario inválido: {fecha} {hora} - {mensaje_validacion}")
            return False, mensaje_validacion
        
        # Intentar agendar cita
        success, message = self.conversation_service.schedule_appointment(fecha, hora, telefono)
        
        if success:
            session["estado"] = "fin"
            return True, None
        else:
            self.conversation_service.add_bot_interaction(
                "Lo siento, hubo un problema al agendar tu cita. Por favor, intenta nuevamente.",
                None
            )
            return False, message


class ConversationService:
    """Servicio principal para manejar conversaciones"""
    
    def __init__(self):
        self.states = {
            "inicio": InitialState(self),
            "evaluacion": EvaluationState(self),
            "profundizacion": DeepeningState(self),
            "derivacion": DeepeningState(self),
            "agendar_cita": AppointmentState(self),
            "fin": None,
        }
        # Singleton: se crea una vez y se reutiliza en todos los requests
        self.ai_service = AIServiceFactory.get_instance()
    
    def initialize_session(self):
        """Inicializa la sesión con valores por defecto"""
        if "fechas_validas" not in session:
            session["fechas_validas"] = {
                'hoy': datetime.now().strftime('%Y-%m-%d'),
                'min_cita': datetime.now().strftime('%Y-%m-%d'),
                'max_cita': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
                'min_sintoma': (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d'),
                'max_sintoma': datetime.now().strftime('%Y-%m-%d')
            }
        
        if "conversacion_data" not in session:
            # Crear conversación básica sin importar de app.py
            conversacion_data = {
                "interacciones": [],
                "sintoma_actual": None,
                "fecha_creacion": datetime.now().isoformat()
            }
            session.update({
                "estado": "inicio",
                "sintoma_actual": None,
                "conversacion_data": conversacion_data
            })
    
    def get_current_state(self) -> Optional[ConversationState]:
        """Obtiene el estado actual de la conversación"""
        estado_actual = session.get("estado", "inicio")
        return self.states.get(estado_actual)
    
    def handle_post_request(self, request_form) -> Tuple[bool, Optional[str]]:
        """Maneja una solicitud POST"""
        estado_actual = self.get_current_state()
        
        if not estado_actual:
            return False, "Estado de conversación no válido"
        
        # Convertir request.form a diccionario
        request_data = {}
        for key in request_form:
            if key == 'sintomas':
                request_data[key] = request_form.getlist(key)
            else:
                request_data[key] = request_form.get(key)
        
        # Manejar la solicitud según el estado
        success, error_message = estado_actual.handle_request(request_data)
        
        return success, error_message
    
    def add_user_interaction(self, message: str):
        """Agrega una interacción del usuario al historial"""
        if "conversacion_data" in session:
            conversacion_data = session["conversacion_data"]
            interaccion = {
                "tipo": "user",
                "mensaje": message,
                "sintoma": session.get("sintoma_actual"),
                "timestamp": datetime.now().isoformat()
            }
            conversacion_data.setdefault("interacciones", []).append(interaccion)
            session["conversacion_data"] = conversacion_data
    
    def add_bot_interaction(self, message: str, sintoma: Optional[str] = None):
        """Agrega una interacción del bot al historial"""
        if "conversacion_data" in session:
            conversacion_data = session["conversacion_data"]
            interaccion = {
                "tipo": "bot",
                "mensaje": message,
                "sintoma": sintoma,
                "timestamp": datetime.now().isoformat()
            }
            conversacion_data.setdefault("interacciones", []).append(interaccion)
            session["conversacion_data"] = conversacion_data
    
    def get_conversation_response(self, user_input: str) -> str:
        """Obtiene una respuesta del sistema conversacional usando Groq API"""
        if detectar_crisis(user_input):
            return CRISIS_RESPONSE

        sintoma = session.get("sintoma_actual")

        try:
            if self.ai_service:
                prompt = (
                    f"El usuario está experimentando: {sintoma}.\n"
                    f'Último mensaje del usuario: "{user_input}"\n\n'
                    "Responde de manera empática, profesional y estructurada."
                )
                response = self.ai_service.generate_response(prompt, sintoma)
                logger.debug("Respuesta Groq recibida correctamente")
                return response
        except Exception as e:
            logger.error(f"Error usando Groq: {e}")

        return "Entiendo que estás pasando por un momento difícil. ¿Te gustaría contarme más sobre cómo te sientes?"
    
    def calculate_duration_days(self, fecha_str: str) -> int:
        """Calcula la duración en días desde una fecha"""
        if not fecha_str:
            return 0
        try:
            fecha_inicio = datetime.strptime(fecha_str, "%Y-%m-%d")
            return (datetime.now() - fecha_inicio).days
        except ValueError:
            return 0
    
    def schedule_appointment(self, fecha: str, hora: str, telefono: str) -> Tuple[bool, str]:
        """Agenda una cita: Calendar + email + persistencia en DB."""
        try:
            sintoma = session.get("sintoma_actual", "Consulta psicológica")
            success, message, calendar_event_id = _agendar_cita_completa(
                fecha, hora, telefono, sintoma
            )

            if not success:
                logger.error(f"Error al agendar cita: {message}")
                return False, message

            # Persistir en la base de datos
            try:
                from services.admin_service import find_or_create_patient
                from models import Appointment as _Appointment
                patient = find_or_create_patient(
                    name="Paciente", phone=telefono, symptom=sintoma
                )
                scheduled_dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
                appt = _Appointment(
                    patient_id=patient.id,
                    scheduled_at=scheduled_dt,
                    symptom=sintoma,
                    status="pending",
                    calendar_event_id=calendar_event_id,
                )
                _db.session.add(appt)
                _db.session.commit()
                logger.info(f"Cita guardada en DB: id={appt.id} {fecha} {hora}")
            except Exception as db_err:
                logger.warning(f"Cita creada en Calendar pero no en DB: {db_err}")

            self.add_bot_interaction(
                f"Cita confirmada\n\n"
                f"Fecha: {fecha}\n"
                f"Hora: {hora}\n"
                f"Telefono: {telefono}\n\n"
                f"Tu cita ha sido registrada correctamente.",
                None,
            )
            self.add_bot_interaction(
                "Gracias por agendar con Equilibra\n\n"
                "Hemos recibido tu solicitud y nos pondremos en contacto contigo pronto.\n"
                "Gracias por confiar en este espacio.",
                None,
            )
            logger.info(f"Cita agendada exitosamente: {fecha} {hora} para {telefono}")
            return True, "Cita agendada exitosamente"

        except Exception as e:
            logger.error(f"Error al agendar cita: {e}")
            return False, str(e)
    
    def reset_session(self) -> None:
        """
        Guarda la conversación activa en DB y reinicia la sesión a estado inicial.
        Llama a esto antes de session.clear() para no perder el historial.
        """
        conv_data = session.get("conversacion_data", {})
        interacciones = conv_data.get("interacciones", [])
        telefono = session.get("telefono_cita")

        if interacciones:
            try:
                patient = _Patient.query.filter_by(phone=telefono).first() if telefono else None
                symptoms = list({i.get("sintoma") for i in interacciones if i.get("sintoma")})
                conv = _ConvModel(
                    patient_id=patient.id if patient else None,
                    session_id=session.get("_id", ""),
                    ended_at=utcnow(),
                )
                conv.messages = interacciones
                conv.detected_symptoms = symptoms
                _db.session.add(conv)
                _db.session.commit()
            except Exception as e:
                logger.warning(f"No se pudo guardar conversación en DB al resetear: {e}")

        session.clear()
        self.initialize_session()

    def cancel_appointment_flow(self) -> None:
        """Cancela el proceso de agendamiento y vuelve al estado de profundización."""
        session["estado"] = "profundizacion"
        self.add_bot_interaction(
            "Entendido, he cancelado el proceso de agendamiento. ¿Hay algo más en lo que pueda ayudarte?",
            session.get("sintoma_actual"),
        )

    def get_template_data(self) -> Dict[str, Any]:
        """Obtiene todos los datos necesarios para renderizar la plantilla"""
        estado_actual = session.get("estado", "inicio")
        
        # Obtener historial de conversación
        conversacion_historial = []
        if "conversacion_data" in session:
            conversacion_data = session["conversacion_data"]
            conversacion_historial = conversacion_data.get("interacciones", [])
        
        # Crear objeto conversacion con estructura compatible con la plantilla
        # La plantilla espera conversacion.historial, no conversacion directamente
        conversacion_obj = type('Conversacion', (), {
            'historial': conversacion_historial
        })()
        
        return {
            "estado": estado_actual,
            "sintomas": SINTOMAS_DISPONIBLES,
            "conversacion": conversacion_obj,  # Objeto con atributo historial
            "sintoma_actual": session.get("sintoma_actual"),
            "fechas_validas": session.get("fechas_validas", {})
        }