"""
Servicio de conversación para manejar la lógica del flujo de conversación en Equilibra.
Implementa State Pattern para manejar los diferentes estados del flujo de conversación.
"""

from datetime import datetime, timedelta
import logging
from typing import Dict, Any, Optional, Tuple
from flask import session, request
from .ai_service import AIServiceFactory
from .validation_service import ValidationService

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


class DeepeningState(ConversationState):
    """Estado de profundización - conversación normal"""
    
    def handle_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        user_input = request_data.get('user_input', '').strip()
        solicitar_cita = request_data.get('solicitar_cita')
        
        # Si el usuario presiona explícitamente el botón de solicitar cita
        if solicitar_cita and solicitar_cita.lower() == "true":
            session["estado"] = "agendar_cita"
            self.conversation_service.add_user_interaction("Quiero agendar una cita")
            
            mensaje = (
                "Excelente decisión. Por favor completa los datos para tu cita presencial:\n\n"
                "📅 Selecciona una fecha disponible\n"
                "⏰ Elige un horario que te convenga\n"
                "📱 Ingresa tu número de teléfono para contactarte"
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
                "⚠️ **Campos incompletos**\n\nPor favor completa todos los campos requeridos para agendar tu cita.",
                None
            )
            logger.warning("Faltan campos en el formulario de cita")
            return False, "Campos incompletos"
        
        # Validar teléfono
        valido, mensaje_error = self.validation_service.validate_phone(telefono)
        if not valido:
            self.conversation_service.add_bot_interaction(
                f"⚠️ {mensaje_error}. Por favor, ingrésalo de nuevo.",
                None
            )
            logger.warning(f"Teléfono inválido: {telefono}")
            return False, mensaje_error
        
        # Validar horario
        es_valido, mensaje_validacion = self.validation_service.validate_appointment_time(fecha, hora)
        if not es_valido:
            self.conversation_service.add_bot_interaction(
                f"⚠️ {mensaje_validacion}. Por favor selecciona otro horario.",
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
                "❌ **Error al agendar**\n\nLo siento, hubo un problema al agendar tu cita. Por favor, intenta nuevamente.",
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
            "derivacion": DeepeningState(self),  # Mismo comportamiento que profundizacion
            "agendar_cita": AppointmentState(self),
            "fin": None  # Estado final
        }
        
        # Inicializar servicios
        self.ai_service = None
        
        # Verificar si GROQ_API_KEY está configurada
        import os
        groq_api_key = os.getenv('GROQ_API_KEY')
        
        if groq_api_key:
            logger.info(f"🔑 GROQ_API_KEY detectada (longitud: {len(groq_api_key)})")
            logger.info("🔄 Intentando inicializar servicio Groq...")
            
            try:
                self.ai_service = AIServiceFactory.create_service("groq")
                logger.info("✅✅✅ SERVICIO GROQ INICIALIZADO CORRECTAMENTE ✅✅✅")
                logger.info(f"📊 Tipo de servicio: {type(self.ai_service).__name__}")
            except Exception as e:
                logger.error(f"❌ Error inicializando servicio Groq: {e}")
                logger.warning("⚠️ Usando servicio de fallback debido a error en Groq")
                self.ai_service = AIServiceFactory.create_service("fallback")
        else:
            logger.warning("⚠️ GROQ_API_KEY NO configurada en variables de entorno")
            logger.info("📋 Usando servicio de fallback por defecto")
            self.ai_service = AIServiceFactory.create_service("fallback")
    
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
        # Detectar crisis primero
        crisis_keywords = ["suicidio", "matarme", "morir", "acabar con todo", "no quiero vivir", "desesperado"]
        if any(keyword in user_input.lower() for keyword in crisis_keywords):
            return "⚠️ **Crisis detectada**\n\nVeo que estás pasando por un momento muy difícil. Es importante que hables con un profesional de inmediato.\n\n📞 **Líneas de ayuda inmediata:**\n• Línea de crisis: 911\n• Tu psicólogo de confianza\n• Servicios de emergencia local\n\nNo estás solo/a, busca ayuda profesional ahora."

        sintoma = session.get("sintoma_actual")

        try:
            if self.ai_service:
                logger.info("🔥 LLAMANDO A GROQ API REALMENTE 🔥")
                prompt = f"""
                El usuario está experimentando: {sintoma}.
                Último mensaje del usuario: "{user_input}"

                Responde de manera empática, profesional y estructurada.
                """
                response = self.ai_service.generate_response(prompt, sintoma)
                logger.info("🎯 RESPUESTA REAL RECIBIDA DE GROQ")
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
        """Agenda una cita (simplificado - la lógica real está en app.py)"""
        # Simulación de agendamiento exitoso
        try:
            mensaje = (
                f"✅ **Cita confirmada**\n\n"
                f"📅 **Fecha:** {fecha}\n"
                f"⏰ **Hora:** {hora}\n"
                f"📱 **Teléfono:** {telefono}\n\n"
                f"Recibirás una llamada para coordinar tu consulta. ¡Gracias por confiar en Equilibra! 🌟"
            )
            
            self.add_bot_interaction(mensaje, None)
            logger.info(f"Cita agendada exitosamente: {fecha} {hora} para {telefono}")
            return True, "Cita agendada exitosamente"
        except Exception as e:
            logger.error(f"Error al agendar cita: {e}")
            return False, str(e)
    
    def get_template_data(self) -> Dict[str, Any]:
        """Obtiene todos los datos necesarios para renderizar la plantilla"""
        # Sintomas disponibles (deben coincidir con los de app.py)
        sintomas_disponibles = [
            "Ansiedad", "Tristeza", "Estrés", "Soledad", "Miedo", "Culpa", "Inseguridad",
            "Enojo", "Agotamiento emocional", "Falta de motivación", "Problemas de sueño",
            "Dolor corporal", "Preocupación excesiva", "Cambios de humor", "Apatía",
            "Sensación de vacío", "Pensamientos negativos", "Llanto frecuente",
            "Dificultad para concentrarse", "Desesperanza", "Tensión muscular",
            "Taquicardia", "Dificultad para respirar", "Problemas de alimentación",
            "Pensamientos intrusivos", "Problemas familiares", "Problemas de pareja"
        ]
        
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
            "sintomas": sintomas_disponibles,
            "conversacion": conversacion_obj,  # Objeto con atributo historial
            "sintoma_actual": session.get("sintoma_actual"),
            "fechas_validas": session.get("fechas_validas", {})
        }