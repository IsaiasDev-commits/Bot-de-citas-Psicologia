from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_from_directory, make_response
from datetime import datetime, timedelta
import os
import smtplib
import json 
import re
import logging
import sys
from logging.handlers import RotatingFileHandler
from functools import lru_cache
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import random
import requests
from environs import Env
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from markupsafe import escape
import threading
import time
from groq import Groq
import html
from typing import Tuple, Optional, List, Dict, Any

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)

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

# Configuración específica para Render
if 'RENDER' in os.environ:
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['SERVER_NAME'] = os.environ.get('RENDER_EXTERNAL_HOSTNAME')

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["2000 per day", "500 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

cita_limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per hour", "30 per minute"],
    storage_uri="memory://",
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
for directory in ["conversaciones", "datos", "logs"]:
    if not os.path.exists(directory):
        os.makedirs(directory)

horarios_cache = {}
cache_lock = threading.Lock()

# ==================== FUNCIONES DE VALIDACIÓN DE HORARIOS ====================

def validar_horario_cita(fecha_str: str, hora_str: str) -> Tuple[bool, str]:
    """
    Validación estricta de horarios de cita
    - No permitir citas en el pasado
    - No permitir citas fuera del horario laboral
    - Restricción de tiempo mínimo para agendar
    """
    try:
        # Combinar fecha y hora
        fecha_hora_cita = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
        ahora = datetime.now()
        
        # 1. No permitir citas en el pasado
        if fecha_hora_cita <= ahora:
            return False, "No se pueden agendar citas en horarios pasados"
        
        # 2. Validar día de la semana
        dia_semana = fecha_hora_cita.weekday()
        if dia_semana == 6:  # Domingo
            return False, "No hay atención los domingos"
        
        # 3. Validar horario laboral según día
        hora_num = int(hora_str.split(':')[0])
        
        if dia_semana in [0, 1, 2, 3, 4]:  # Lunes a Viernes
            if not (14 <= hora_num <= 19):
                return False, "Horario no disponible. Lunes a Viernes: 14:00 - 19:00"
        elif dia_semana == 5:  # Sábado
            if not (8 <= hora_num <= 14):
                return False, "Horario no disponible. Sábados: 08:00 - 14:00"
        
        # 4. Restricción de tiempo mínimo para agendar (30 minutos)
        tiempo_minimo_agendamiento = timedelta(minutes=30)
        if fecha_hora_cita - ahora < tiempo_minimo_agendamiento:
            return False, "Debe agendar con al menos 30 minutos de anticipación"
        
        # 5. Restricción adicional: No permitir agendar para el mismo día después de las 18:00
        if (fecha_hora_cita.date() == ahora.date() and 
            ahora.hour >= 18 and hora_num >= 18):
            return False, "No se pueden agendar citas para hoy después de las 18:00"
            
        return True, "Horario válido"
        
    except ValueError as e:
        return False, f"Formato de fecha/hora inválido: {str(e)}"

def obtener_horarios_disponibles_estrictos(fecha_str: str) -> List[Dict[str, Any]]:
    """
    Obtener horarios disponibles con validaciones estrictas
    """
    try:
        fecha_cita = datetime.strptime(fecha_str, "%Y-%m-%d")
        dia_semana = fecha_cita.weekday()
        ahora = datetime.now()
        es_hoy = fecha_cita.date() == ahora.date()
        
        # Definir horarios base según día
        if dia_semana in [0, 1, 2, 3, 4]:  # Lunes a Viernes
            horarios_base = ["14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]
        elif dia_semana == 5:  # Sábado
            horarios_base = ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]
        else:  # Domingo
            return []
        
        horarios_filtrados = []
        
        for hora in horarios_base:
            # Validación estricta para cada horario
            es_valido, mensaje = validar_horario_cita(fecha_str, hora)
            
            if es_valido:
                # Verificación adicional: para hoy, filtrar horarios que ya pasaron
                if es_hoy:
                    hora_actual = ahora.hour
                    minuto_actual = ahora.minute
                    hora_cita = int(hora.split(':')[0])
                    
                    # Si la hora de la cita ya pasó, no mostrar
                    if hora_cita < hora_actual or (hora_cita == hora_actual and minuto_actual >= 0):
                        continue
                
                horarios_filtrados.append({
                    'hora': hora,
                    'disponible': True,
                    'mensaje': 'Disponible'
                })
        
        return horarios_filtrados
        
    except ValueError:
        return []

class SistemaAprendizaje:
    def __init__(self):
        self.respuestas_efectivas = {}  
        self.patrones_conversacion = {}  
        self.archivo_aprendizaje = "datos/aprendizaje.json"
        self.lock = threading.Lock()  
        self.cargar_aprendizaje()
    
    def cargar_aprendizaje(self):
        try:
            with self.lock:
                if os.path.exists(self.archivo_aprendizaje):
                    with open(self.archivo_aprendizaje, 'r', encoding='utf-8') as f:
                        datos = json.load(f)
                        self.respuestas_efectivas = datos.get('respuestas_efectivas', {})
                        self.patrones_conversacion = datos.get('patrones_conversacion', {})
        except Exception as e:
            app.logger.error(f"Error cargando aprendizaje: {e}")
    
    def guardar_aprendizaje(self):
        try:
            with self.lock:
                os.makedirs(os.path.dirname(self.archivo_aprendizaje), exist_ok=True)
                with open(self.archivo_aprendizaje, 'w', encoding='utf-8') as f:
                    json.dump({
                        'respuestas_efectivas': self.respuestas_efectivas,
                        'patrones_conversacion': self.patrones_conversacion
                    }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            app.logger.error(f"Error guardando aprendizaje: {e}")
    
    def evaluar_respuesta(self, sintoma, respuesta_usuario, respuesta_bot, engagement):
        if not isinstance(sintoma, str) or not sintoma.strip():
            return
            
        if not isinstance(respuesta_bot, str) or not respuesta_bot.strip():
            return
            
        efectividad = min(10, max(1, engagement))
        
        if sintoma not in self.respuestas_efectivas:
            self.respuestas_efectivas[sintoma] = {}
        
        if respuesta_bot not in self.respuestas_efectivas[sintoma]:
            self.respuestas_efectivas[sintoma][respuesta_bot] = {
                'efectividad_total': 0,
                'veces_usada': 0,
                'ultimo_uso': datetime.now().isoformat()
            }
        
        self.respuestas_efectivas[sintoma][respuesta_bot]['efectividad_total'] += efectividad
        self.respuestas_efectivas[sintoma][respuesta_bot]['veces_usada'] += 1
        self.respuestas_efectivas[sintoma][respuesta_bot]['ultimo_uso'] = datetime.now().isoformat()
        
        self.guardar_aprendizaje()
    
    def obtener_mejor_respuesta(self, sintoma, contexto):
        if sintoma in self.respuestas_efectivas and self.respuestas_efectivas[sintoma]:
            respuestas_ordenadas = sorted(
                self.respuestas_efectivas[sintoma].items(),
                key=lambda x: x[1]['efectividad_total'] / x[1]['veces_usada'] if x[1]['veces_usada'] > 0 else 0,
                reverse=True
            )
            
            for respuesta, stats in respuestas_ordenadas[:3]: 
                ultimo_uso = datetime.fromisoformat(stats['ultimo_uso'])
                if (datetime.now() - ultimo_uso).total_seconds() > 3600:
                    return respuesta
        
        return None  

def generar_respuesta_llm(prompt, modelo="openai/gpt-oss-120b"):
    try:
        api_key = os.getenv('GROQ_API_KEY')
        if not api_key:
            app.logger.error("GROQ_API_KEY no configurada")
            return None
            
        client = Groq(api_key=api_key, timeout=30)
        
        completion = client.chat.completions.create(
            model=modelo,
            messages=[
                {
                    "role": "system",
                    "content": """Eres Equilibra, un asistente psicológico empático y profesional. 
                    Tu objetivo es ayudar a las personas a reflexionar sobre sus emociones y, 
                    cuando sea apropiado, sugerir una cita con un psicólogo profesional.
                    
                    DIRECTRICES:
                    1. Responde de manera comprensiva, breve (2-3 oraciones) y natural
                    2. Sé empático pero profesional
                    3. Haz preguntas abiertas para profundizar
                    4. Valida las emociones del usuario
                    5. Ofrece perspectivas útiles pero no des diagnósticos
                    6. Después de 2-3 interacciones, sugiere amablemente una cita presencial
                    7. Si el usuario menciona crisis grave, derívalo inmediatamente a ayuda profesional
                    
                    IMPORTANTE: NO sugieras cita si el usuario no la ha solicitado explícitamente.
                    """
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=250,
            top_p=0.9,
            stream=False,
            timeout=30
        )
        
        respuesta = completion.choices[0].message.content.strip()
        
        # Verificar si la respuesta está truncada 
        if respuesta and (respuesta.endswith('...') or not respuesta.endswith(('.', '!', '?'))):
            app.logger.warning(f"Respuesta posiblemente truncada: {respuesta}")
            # Intentar con un modelo alternativo
            return generar_respuesta_llm(prompt, modelo="llama-3.3-70b-versatile")
        
        return respuesta
    
    except Exception as e:
        app.logger.error(f"Error al generar respuesta con Groq: {e}")
        return None

def sanitizar_input(texto):
    if not texto:
        return ""
    texto = html.escape(texto)
    texto = re.sub(r'[<>{}[\]();]', '', texto)
    return texto[:500] if len(texto) > 500 else texto

def validar_telefono(telefono) -> Tuple[bool, str]:
    if not telefono:
        return False, "Teléfono requerido"
    
    telefono_limpio = re.sub(r'[^\d]', '', telefono)
    
    if len(telefono_limpio) != 10:
        return False, "El teléfono debe tener 10 dígitos"
    
    if not telefono_limpio.startswith('09'):
        return False, "El teléfono debe comenzar con 09"
    
    return True, ""

def calcular_duracion_dias(fecha_str):
    if not fecha_str:
        return 0
    try:
        fecha_inicio = datetime.strptime(fecha_str, "%Y-%m-%d")
        return (datetime.now() - fecha_inicio).days
    except ValueError:
        return 0

def detectar_crisis(texto):
    patrones_crisis = [
        r'suicidio', r'autolesión', r'autoflagelo', r'matarme', 
        r'no\s+quiero\s+vivir', r'acabar\s+con\s+todo', 
        r'no\s+vale\s+la\s+pena', r'sin\s+esperanza', 
        r'quiero\s+morir', r'terminar\s+con\s+todo'
    ]
    
    texto = texto.lower()
    for patron in patrones_crisis:
        if re.search(patron, texto):
            return True
    return False

sintomas_disponibles = [
    "Ansiedad", "Tristeza", "Estrés", "Soledad", "Miedo", "Culpa", "Inseguridad",
    "Enojo", "Agotamiento emocional", "Falta de motivación", "Problemas de sueño",
    "Dolor corporal", "Preocupación excesiva", "Cambios de humor", "Apatía",
    "Sensación de vacío", "Pensamientos negativos", "Llanto frecuente",
    "Dificultad para concentrarse", "Desesperanza", "Tensión muscular",
    "Taquicardia", "Dificultad para respirar", "Problemas de alimentación",
    "Pensamientos intrusivos", "Problemas familiares", "Problemas de pareja"
]

respuestas_por_sintoma = {
    "Ansiedad": [
        "La ansiedad puede ser abrumadora. ¿Qué situaciones la desencadenan?",
        "Cuando sientes ansiedad, ¿qué técnicas has probado para calmarte?",
        "¿Notas que la ansiedad afecta tu cuerpo (ej. taquicardia, sudoración)?",
        "Vamos a respirar juntos: inhala por 4 segundos, exhala por 6. ¿Te ayuda?",
        "¿Hay algo que solía relajarte y ahora ya no funciona?",
        "¿Sientes síntomas como opresión en el pecho o dificultad para respirar?",
        "Tu cuerpo también habla cuando tu mente está saturada, escúchalo sin juzgar.",
        "A veces, lo que más ayuda es hablar sin miedo a ser juzgado.",
        "No necesitas resolver todo hoy. ¿Qué necesitas en este momento?",
        "¿Qué pensamientos suelen venir justo antes de que inicie la ansiedad?"
    ],
    "Tristeza": [
        "Sentir tristeza no significa debilidad. Es una señal de que algo importa.",
        "¿Qué eventos recientes han influido en tu estado de ánimo?",
        "Permítete sentir. Reprimir emociones no las hace desaparecer.",
        "¿Te has dado permiso para descansar o simplemente estar contigo?",
        "¿Hay música, recuerdos o espacios que antes te aliviaban?",
        "Es posible que tu cuerpo también necesite descanso emocional.",
        "¿Cómo expresarías tu tristeza si fuera una historia o una imagen?",
        "Estás haciendo lo mejor que puedes. Validar eso ya es un paso enorme.",
        "¿Has probado escribir lo que sientes, sin filtros ni juicios?",
        "Estoy contigo en esto. ¿Qué necesitarías hoy para sentirte un poco mejor?"
    ],
    # ... (mantener el resto de respuestas_por_sintoma igual)
    # Para ahorrar espacio, mantengo la estructura pero elimino el contenido detallado
}

class SistemaConversacional:
    def __init__(self):
        self.historial = []
        self.contador_interacciones = 0
        self.contexto_actual = None
        self.sistema_aprendizaje = SistemaAprendizaje()
        self.engagement_actual = 5
        self.max_historial = 100

    def to_dict(self):
        return {
            'historial': self.historial[-self.max_historial:],
            'contador_interacciones': self.contador_interacciones,
            'contexto_actual': self.contexto_actual,
            'engagement_actual': self.engagement_actual
        }
    
    @classmethod
    def from_dict(cls, data):
        instance = cls()
        instance.historial = data.get('historial', [])
        instance.contador_interacciones = data.get('contador_interacciones', 0)
        instance.contexto_actual = data.get('contexto_actual', None)
        instance.engagement_actual = data.get('engagement_actual', 5)
        return instance

    def obtener_respuesta_predefinida(self, sintoma):
        respuestas_genericas = [
            "Entiendo que estés pasando por un momento difícil. ¿Qué has intentado para manejar esta situación?",
            "Es completamente normal sentirse así. ¿Te gustaría hablar más sobre qué desencadenó estos sentimientos?",
            "Agradezco que compartas esto conmigo. ¿Cómo ha afectado esto tu día a día?",
            "Parece que esto te está afectando profundamente. ¿Puedes contarme un poco más?",
            "Tu bienestar es importante. ¿Qué crees que podría ayudarte en este momento?",
        ]
        return random.choice(respuestas_genericas)

    def obtener_respuesta_ia(self, sintoma, user_input):
        try:
            contexto = f"""
            El usuario está experimentando: {sintoma}. 
            Historial reciente: {str(self.historial[-2:]) if len(self.historial) > 2 else 'Primera interacción'}
            Último mensaje del usuario: "{user_input}"
            
            Por favor, responde de manera empática y profesional.
            IMPORTANTE: NO sugieras cita a menos que el usuario la solicite explícitamente.
            """
            
            respuesta = generar_respuesta_llm(contexto, modelo="openai/gpt-oss-120b")
            
            modelos_alternativos = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
            
            if not respuesta or len(respuesta) < 10:
                for modelo in modelos_alternativos:
                    respuesta = generar_respuesta_llm(contexto, modelo=modelo)
                    if respuesta and len(respuesta) >= 10:
                        break
            
            if respuesta and len(respuesta) > 10:
                return respuesta
        except Exception as e:
            app.logger.error(f"Error al obtener respuesta de IA: {e}")
        
        return self.obtener_respuesta_predefinida(sintoma)

    def obtener_respuesta(self, sintoma, user_input):
        if detectar_crisis(user_input):
            return "⚠️ Veo que estás pasando por un momento muy difícil. Es importante que hables con un profesional de inmediato. Por favor, comunícate con la línea de crisis al 911 or con tu psicólogo de confianza."

        # Intentar con respuesta aprendida primero
        respuesta_aprendida = self.sistema_aprendizaje.obtener_mejor_respuesta(sintoma, user_input)
        if respuesta_aprendida:
            app.logger.info(f"Usando respuesta aprendida para {sintoma}")
            self.contador_interacciones += 1
            return respuesta_aprendida

        # Si no hay respuesta aprendida, usar IA
        respuesta_ia = self.obtener_respuesta_ia(sintoma, user_input)
        self.contador_interacciones += 1
        
        # Aprender de esta interacción
        self.aprender_de_interaccion(sintoma, user_input, respuesta_ia)
        
        return respuesta_ia

    def aprender_de_interaccion(self, sintoma, user_input, respuesta_bot):
        engagement = min(10, len(user_input) / 10)
        self.sistema_aprendizaje.evaluar_respuesta(sintoma, user_input, respuesta_bot, engagement)
        self.aprender_patrones(user_input, respuesta_bot)

    def aprender_patrones(self, user_input, respuesta_bot):
        palabras_usuario = set(user_input.lower().split())
        palabras_bot = set(respuesta_bot.lower().split())
        
        for palabra in palabras_usuario:
            if palabra not in self.sistema_aprendizaje.patrones_conversacion:
                self.sistema_aprendizaje.patrones_conversacion[palabra] = {}
            
            for palabra_bot in palabras_bot:
                if palabra_bot not in self.sistema_aprendizaje.patrones_conversacion[palabra]:
                    self.sistema_aprendizaje.patrones_conversacion[palabra][palabra_bot] = 0
                self.sistema_aprendizaje.patrones_conversacion[palabra][palabra_bot] += 1
        
        self.sistema_aprendizaje.guardar_aprendizaje()

    def agregar_interaccion(self, tipo, mensaje, sintoma=None):
        if len(self.historial) >= self.max_historial:
            self.historial.pop(0)
            
        interaccion = {
            'tipo': tipo,
            'mensaje': mensaje,
            'sintoma': sintoma,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        }
        self.historial.append(interaccion)
        
        if tipo == 'user' and len(self.historial) > 1:
            ultima_respuesta_bot = self.historial[-2] if self.historial[-2]['tipo'] == 'bot' else None
            if ultima_respuesta_bot:
                self.engagement_actual = min(10, len(mensaje) / 15)
                self.aprender_de_interaccion(
                    ultima_respuesta_bot['sintoma'] or "general",
                    mensaje,
                    ultima_respuesta_bot['mensaje']
                )

def get_calendar_service():
    try:
        google_credentials = os.getenv('GOOGLE_CREDENTIALS')
        if not google_credentials:
            app.logger.error("GOOGLE_CREDENTIALS no configuradas")
            return None
        
        # Limpiar posibles espacios extras
        google_credentials = google_credentials.strip()
        
        app.logger.info(f"Longitud de credenciales: {len(google_credentials)}")
        
        try:
            creds_dict = json.loads(google_credentials)
            app.logger.info("✅ Credenciales JSON parseadas correctamente")
        except json.JSONDecodeError as e:
            app.logger.error(f"❌ Error parseando JSON: {e}")
            # Mostrar dónde está el error
            app.logger.error(f"Error alrededor del carácter: {e.pos}")
            app.logger.error(f"Texto alrededor: ...{google_credentials[max(0,e.pos-50):e.pos+50]}...")
            return None
            
        # Verificar campos requeridos
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        for field in required_fields:
            if field not in creds_dict:
                app.logger.error(f"❌ Campo requerido faltante: {field}")
                return None
        
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        
        service = build('calendar', 'v3', credentials=creds)
        app.logger.info("✅ Servicio de calendario creado exitosamente")
        return service
        
    except Exception as e:
        app.logger.error(f"Error al obtener servicio de calendario: {e}")
        return None

def crear_evento_calendar(fecha, hora, telefono, sintoma):
    try:
        # Validar fecha y hora
        datetime.strptime(fecha, "%Y-%m-%d")
        datetime.strptime(hora, "%H:%M")
        
        service = get_calendar_service()
        if not service:
            app.logger.error("No se pudo obtener el servicio de calendario")
            return None
            
        # Crear el evento con formato mejorado
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
        
        app.logger.info(f"Intentando crear evento: {fecha} {hora} para {telefono}")
        
        # Intentar crear el evento
        event_created = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
        
        evento_url = event_created.get('htmlLink')
        app.logger.info(f"✅ Evento creado exitosamente: {evento_url}")
        
        return evento_url
        
    except ValueError as ve:
        app.logger.error(f"❌ Formato de fecha/hora inválido: {ve}")
        return None
    except HttpError as error:
        app.logger.error(f"❌ Error de Google Calendar API: {error}")
        # Mostrar más detalles del error
        if error.resp.status == 403:
            app.logger.error("❌ Error 403: Permisos insuficientes. Verifica que la cuenta de servicio tenga permisos de escritura.")
        elif error.resp.status == 404:
            app.logger.error("❌ Error 404: Calendario no encontrado.")
        return None
    except Exception as e:
        app.logger.error(f"❌ Error inesperado al crear evento: {e}")
        return None

def enviar_correo_confirmacion(destinatario, fecha, hora, telefono, sintoma):
    remitente = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")
    
    if not remitente or not password:
        app.logger.error("Credenciales de email no configuradas")
        return False
    
    mensaje = MIMEMultipart()
    mensaje['From'] = remitente
    mensaje['To'] = destinatario
    mensaje['Subject'] = f"Nueva cita agendada - {fecha} {hora}"
    
    cuerpo = f"""
    📅 Nueva cita agendada:
    Fecha: {fecha}
    Hora: {hora}
    Teléfono: {telefono}
    Síntoma principal: {sintoma}
    
    Nueva cita agendada.
    """
    mensaje.attach(MIMEText(cuerpo, 'plain'))
    
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(remitente, password)
            server.send_message(mensaje)
        app.logger.info(f"Correo de confirmación enviado a {destinatario}")
        return True
    except Exception as e:
        app.logger.error(f"Error enviando correo: {e}")
        return False

def limpiar_datos_aprendizaje():
    try:
        while True:
            time.sleep(24 * 60 * 60)
            
            sistema_aprendizaje = SistemaAprendizaje()
            if not sistema_aprendizaje.respuestas_efectivas:
                continue
            
            for sintoma in list(sistema_aprendizaje.respuestas_efectivas.keys()):
                for respuesta in list(sistema_aprendizaje.respuestas_efectivas[sintoma].keys()):
                    stats = sistema_aprendizaje.respuestas_efectivas[sintoma][respuesta]
                    ultimo_uso = datetime.fromisoformat(stats['ultimo_uso'])
                    
                    if (datetime.now() - ultimo_uso).days > 30 or stats['veces_usada'] < 2:
                        del sistema_aprendizaje.respuestas_efectivas[sintoma][respuesta]
                
                if not sistema_aprendizaje.respuestas_efectivas[sintoma]:
                    del sistema_aprendizaje.respuestas_efectivas[sintoma]
            
            sistema_aprendizaje.guardar_aprendizaje()
            app.logger.info("Limpieza automática de datos de aprendizaje completada")
            
    except Exception as e:
        app.logger.error(f"Error limpiando datos de aprendizaje: {e}")

def limpiar_cache_horarios():
    try:
        while True:
            time.sleep(3600)
            with cache_lock:
                now = time.time()
                keys_to_delete = []
                for key, (timestamp, _) in horarios_cache.items():
                    if now - timestamp > 1800:
                        keys_to_delete.append(key)
                
                for key in keys_to_delete:
                    del horarios_cache[key]
                
                app.logger.info(f"Cache de horarios limpiado. Eliminadas {len(keys_to_delete)} entradas.")
    except Exception as e:
        app.logger.error(f"Error limpiando cache de horarios: {e}")

def verificar_disponibilidad_atomica(fecha: str, hora: str) -> Dict[str, Any]:
    """Verificación atómica estricta con todas las validaciones"""
    try:
        # 1. Validación básica de formato
        datetime.strptime(fecha, "%Y-%m-%d")
        datetime.strptime(hora, "%H:%M")
        
        # 2. Validación estricta de horario
        es_valido, mensaje = validar_horario_cita(fecha, hora)
        if not es_valido:
            app.logger.warning(f"❌ Validación fallida para {fecha} {hora}: {mensaje}")
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
        
        # Verificar superposición estricta
        hora_solicitada_start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        hora_solicitada_end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        for evento in eventos.get('items', []):
            evento_start_str = evento['start'].get('dateTime', evento['start'].get('date'))
            evento_end_str = evento['end'].get('dateTime', evento['end'].get('date'))
            
            if 'T' in evento_start_str:
                try:
                    evento_start = datetime.fromisoformat(evento_start_str.replace('Z', '+00:00'))
                    evento_end = datetime.fromisoformat(evento_end_str.replace('Z', '+00:00'))
                    
                    if (evento_start < hora_solicitada_end and evento_end > hora_solicitada_start):
                        app.logger.warning(f"❌ Verificación atómica: Horario {hora} ocupado por {evento.get('summary', 'Sin título')}")
                        return {"disponible": False, "error": "Horario ya ocupado"}
                except ValueError:
                    continue
        
        app.logger.info(f"✅ Horario {fecha} {hora} disponible y válido")
        return {"disponible": True}
        
    except Exception as e:
        app.logger.error(f"Error en verificación atómica: {e}")
        return {"disponible": False, "error": str(e)}

# Iniciar hilos de limpieza solo si no estamos en entorno de testing
if os.environ.get('FLASK_ENV') == 'production' and not os.environ.get('TESTING'):
    try:
        hilo_limpieza = threading.Thread(target=limpiar_datos_aprendizaje, daemon=True)
        hilo_limpieza.start()
        
        hilo_limpieza_cache = threading.Thread(target=limpiar_cache_horarios, daemon=True)
        hilo_limpieza_cache.start()
        app.logger.info("Hilos de limpieza iniciados")
    except Exception as e:
        app.logger.error(f"Error iniciando hilos de limpieza: {e}")

@app.route("/", methods=["GET", "POST"])
@limiter.limit("500 per hour")
def index():
    if "fechas_validas" not in session:
        session["fechas_validas"] = {
            'hoy': datetime.now().strftime('%Y-%m-%d'),
            'min_cita': datetime.now().strftime('%Y-%m-%d'),
            'max_cita': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'min_sintoma': (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d'),
            'max_sintoma': datetime.now().strftime('%Y-%m-%d')
        }

    if "conversacion_data" not in session:
        conversacion = SistemaConversacional()
        session.update({
            "estado": "inicio",
            "sintoma_actual": None,
            "conversacion_data": conversacion.to_dict()
        })
    else:
        conversacion = SistemaConversacional.from_dict(session["conversacion_data"])

    if request.method == "POST":
        estado_actual = session["estado"]
        
        app.logger.info(f"Estado actual: {estado_actual}, datos del formulario: {dict(request.form)}")

        if estado_actual == "inicio":
            if sintomas := request.form.getlist("sintomas"):
                if not sintomas:
                    return render_template("index.html", error="Por favor selecciona un síntoma")
                
                session["sintoma_actual"] = sintomas[0]
                session["estado"] = "evaluacion"
                conversacion.agregar_interaccion('bot', f"Entiendo que estás experimentando {sintomas[0].lower()}. ¿Desde cuándo lo notas?", sintomas[0])
                app.logger.info(f"Usuario seleccionó síntoma: {sintomas[0]}")

        elif estado_actual == "evaluacion":
            if fecha := request.form.get("fecha_inicio_sintoma"):
                duracion = calcular_duracion_dias(fecha)
                session["estado"] = "profundizacion"
                
                if duracion < 30:
                    comentario = "Es bueno que lo identifiques temprano."
                elif duracion < 365:
                    comentario = "Varios meses con esto... debe ser difícil."
                else:
                    comentario = "Tu perseverancia es admirable."
                
                respuesta = conversacion.obtener_respuesta(session["sintoma_actual"], "")
                conversacion.agregar_interaccion('bot', f"{comentario} {respuesta}", session["sintoma_actual"])

        elif estado_actual in ["profundizacion", "derivacion"]:
            user_input = sanitizar_input(request.form.get("user_input", "").strip())
            solicitar_cita = request.form.get("solicitar_cita")
            
            # SOLO si el usuario presiona explícitamente el botón de solicitar cita
            if solicitar_cita and solicitar_cita.lower() == "true":
                # El usuario hizo clic en el botón de solicitar cita - IR DIRECTAMENTE A AGENDAR
                session["estado"] = "agendar_cita"
                conversacion.agregar_interaccion('user', "Quiero agendar una cita", session["sintoma_actual"])
                
                mensaje = (
                    "Excelente decisión. Por favor completa los datos para tu cita presencial:\n\n"
                    "📅 Selecciona una fecha disponible\n"
                    "⏰ Elige un horario que te convenga\n"
                    "📱 Ingresa tu número de teléfono para contactarte"
                )
                conversacion.agregar_interaccion('bot', mensaje, session["sintoma_actual"])
                app.logger.info("Usuario solicitó cita mediante botón - Saltando a agendamiento")
                
            elif user_input:
                # El usuario envió un mensaje de texto - CONVERSACIÓN NORMAL SIN DETECCIÓN AUTOMÁTICA DE CITA
                conversacion.agregar_interaccion('user', user_input, session["sintoma_actual"])
                
                # Solo responde normalmente
                respuesta = conversacion.obtener_respuesta(session["sintoma_actual"], user_input)
                conversacion.agregar_interaccion('bot', respuesta, session["sintoma_actual"])

        elif estado_actual == "agendar_cita":
            if request.form.get("cancelar_cita"):
                session["estado"] = "profundizacion"
                conversacion.agregar_interaccion('bot', "Entendido, no hay problema. ¿Hay algo más en lo que pueda ayudarte hoy?", session["sintoma_actual"])
                app.logger.info("Usuario canceló proceso de cita")
            else:
                fecha = request.form.get("fecha_cita")
                telefono = request.form.get("telefono", "").strip()
                # USAR hora_seleccionada EN LUGAR DE hora_cita
                hora = request.form.get("hora_seleccionada")

                if fecha and telefono and hora:
                    valido, mensaje_error = validar_telefono(telefono)
                    if not valido:
                        conversacion.agregar_interaccion('bot', f"⚠️ {mensaje_error}. Por favor, ingrésalo de nuevo.", None)
                        app.logger.warning(f"Teléfono inválido: {telefono}")
                    else:
                        # Validación estricta de horario antes de agendar
                        es_valido, mensaje_validacion = validar_horario_cita(fecha, hora)
                        if not es_valido:
                            conversacion.agregar_interaccion('bot', f"⚠️ {mensaje_validacion}. Por favor selecciona otro horario.", None)
                            app.logger.warning(f"Horario inválido: {fecha} {hora} - {mensaje_validacion}")
                        else:
                            cita = {
                                "fecha": fecha,
                                "hora": hora,
                                "telefono": telefono
                            }

                            evento_url = crear_evento_calendar(
                                cita["fecha"],
                                cita["hora"],
                                cita["telefono"],
                                session["sintoma_actual"]
                            )

                            if evento_url:
                                if enviar_correo_confirmacion(
                                    os.getenv("PSICOLOGO_EMAIL"),
                                    cita["fecha"],
                                    cita["hora"],
                                    cita["telefono"],
                                    session["sintoma_actual"]
                                ):
                                    mensaje = (
                                        f"✅ Cita confirmada para {cita['fecha']} a las {cita['hora']}. " 
                                        "Recibirás una llamada para coordinar tu consulta. " 
                                        "¡Gracias por confiar en nosotros!"
                                    )
                                else:
                                    mensaje = "✅ Cita registrada (pero error al notificar al profesional)"

                                conversacion.agregar_interaccion('bot', mensaje, None)
                                session["estado"] = "fin"
                                app.logger.info(f"Cita agendada exitosamente: {cita}")
                            else:
                                conversacion.agregar_interaccion('bot', "❌ Error al agendar. Intenta nuevamente", None)
                                app.logger.error(f"Error al agendar cita: {cita}")
                else:
                    conversacion.agregar_interaccion('bot', "⚠️ Por favor completa todos los campos requeridos.", None)
                    app.logger.warning("Faltan campos en el formulario de cita")

        session["conversacion_data"] = conversacion.to_dict()
        return redirect(url_for("index"))

    session["conversacion_data"] = conversacion.to_dict()
    return render_template(
        "index.html",
        estado=session["estado"],
        sintomas=sintomas_disponibles,
        conversacion=conversacion,
        sintoma_actual=session.get("sintoma_actual"),
        fechas_validas=session["fechas_validas"]
    )

@app.route("/reset", methods=["POST"])
@limiter.limit("50 per hour")
def reset():
    try:
        session.clear()
        conversacion = SistemaConversacional()
        session["conversacion_data"] = conversacion.to_dict()
        session["estado"] = "inicio"
        session["sintoma_actual"] = None
        session["fechas_validas"] = {
            'hoy': datetime.now().strftime('%Y-%m-%d'),
            'min_cita': datetime.now().strftime('%Y-%m-%d'),
            'max_cita': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'min_sintoma': (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d'),
            'max_sintoma': datetime.now().strftime('%Y-%m-%d')
        }
        
        app.logger.info("Sesión reiniciada por el usuario")
        return jsonify({"status": "success"})
    except Exception as e:
        app.logger.error(f"Error al reiniciar sesión: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cancelar_cita", methods=["POST"])
@limiter.limit("50 per hour")
def cancelar_cita():
    try:
        if "conversacion_data" in session:
            conversacion = SistemaConversacional.from_dict(session["conversacion_data"])
            session["estado"] = "profundizacion"
            conversacion.agregar_interaccion('bot', "Entendido, he cancelado el proceso de agendamiento de cita. ¿Hay algo más en lo que pueda ayudarte?", session.get("sintoma_actual"))
            session["conversacion_data"] = conversacion.to_dict()
        
        return jsonify({"status": "success", "message": "Proceso de cita cancelado"})
    except Exception as e:
        app.logger.error(f"Error al cancelar cita: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/verificar-horario", methods=["POST"])
@cita_limiter.limit("60 per minute")
def verificar_horario():
    try:
        data = request.get_json()
        if not data or 'fecha' not in data or 'hora' not in data:
            return jsonify({"error": "Datos incompletos"}), 400
        
        fecha = data['fecha']
        hora = data['hora']
        
        # Validar formato de fecha y hora
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
            datetime.strptime(hora, "%H:%M")
        except ValueError:
            return jsonify({"error": "Formato de fecha u hora inválido"}), 400
        
        cache_key = f"{fecha}_{hora}"
        current_time = time.time()
        
        with cache_lock:
            if cache_key in horarios_cache:
                cache_time, cached_result = horarios_cache[cache_key]
                if current_time - cache_time < 30:  # 30 segundos de cache
                    app.logger.info(f"Usando cache para {cache_key}")
                    return jsonify(cached_result)
        
        service = get_calendar_service()
        if not service:
            app.logger.error("Servicio de calendario no disponible")
            return jsonify({"error": "Servicio de calendario no disponible"}), 500
            
        # VERIFICACIÓN ESTRICTA - Buscar eventos que se superpongan
        start_time = f"{fecha}T{hora}:00-05:00"
        end_time = f"{fecha}T{int(hora.split(':')[0])+1}:00:00-05:00"
        
        # Buscar eventos en un rango más amplio para detectar superposiciones
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
        
        # Verificar si hay eventos que se superpongan con el horario solicitado
        disponible = True
        hora_solicitada_start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        hora_solicitada_end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        for evento in eventos.get('items', []):
            evento_start_str = evento['start'].get('dateTime', evento['start'].get('date'))
            evento_end_str = evento['end'].get('dateTime', evento['end'].get('date'))
            
            try:
                # Convertir tiempos del evento
                if 'T' in evento_start_str:
                    evento_start = datetime.fromisoformat(evento_start_str.replace('Z', '+00:00'))
                    evento_end = datetime.fromisoformat(evento_end_str.replace('Z', '+00:00'))
                    
                    # Verificar superposición estricta
                    if (evento_start < hora_solicitada_end and evento_end > hora_solicitada_start):
                        app.logger.info(f"❌ Horario {hora} ocupado por evento: {evento.get('summary', 'Sin título')}")
                        disponible = False
                        break
                        
            except ValueError as e:
                app.logger.warning(f"Error parsing event time: {e}")
                continue
        
        app.logger.info(f"Horario {fecha} {hora}: {'✅ DISPONIBLE' if disponible else '❌ OCUPADO'}")
        
        with cache_lock:
            horarios_cache[cache_key] = (current_time, {
                "disponible": disponible,
                "timestamp": current_time
            })
        
        return jsonify({"disponible": disponible})
        
    except HttpError as error:
        app.logger.error(f"Error de Google API: {error}")
        return jsonify({"error": "Error de calendario"}), 500
    except Exception as e:
        app.logger.error(f"Error inesperado al verificar horario: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route("/obtener-horarios-disponibles", methods=["POST"])
@cita_limiter.limit("60 per minute")
def obtener_horarios_disponibles():
    """Endpoint para obtener horarios disponibles con validaciones estrictas"""
    try:
        data = request.get_json()
        if not data or 'fecha' not in data:
            return jsonify({"error": "Fecha requerida"}), 400
        
        fecha = data['fecha']
        
        # Validar formato de fecha
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Formato de fecha inválido"}), 400
        
        # Obtener horarios disponibles con validaciones estrictas
        horarios_disponibles = obtener_horarios_disponibles_estrictos(fecha)
        
        return jsonify(horarios_disponibles)
        
    except Exception as e:
        app.logger.error(f"Error obteniendo horarios disponibles: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route("/agendar-cita", methods=["POST"])
@cita_limiter.limit("40 per minute")
def agendar_cita():
    try:
        data = request.get_json()
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
        
        # 1. Validar teléfono
        valido, mensaje_error = validar_telefono(telefono)
        if not valido:
            return jsonify({"error": mensaje_error}), 400
        
        # 2. Validación estricta de horario
        es_valido, mensaje_validacion = validar_horario_cita(fecha, hora)
        if not es_valido:
            return jsonify({"error": mensaje_validacion}), 400
        
        # 3. Revisar disponibilidad justo antes de agendar (VERIFICACIÓN ESTRICTA)
        verificacion = verificar_disponibilidad_atomica(fecha, hora)
        if not verificacion["disponible"]:
            return jsonify({"error": verificacion.get("error", "El horario ya no está disponible")}), 409
        
        # 4. Crear evento en calendario
        evento_url = crear_evento_calendar(fecha, hora, telefono, sintoma)
        
        if not evento_url:
            return jsonify({"error": "Error al crear la cita en el calendario"}), 500
            
        # 5. Enviar correo de confirmación
        if not enviar_correo_confirmacion(
            os.getenv("PSICOLOGO_EMAIL"),
            fecha,
            hora,
            telefono,
            sintoma
        ):
            app.logger.warning("Cita agendada pero error al enviar correo de confirmación")
            
        # 6. Limpiar cache para esta fecha/hora
        with cache_lock:
            cache_key = f"{fecha}_{hora}"
            if cache_key in horarios_cache:
                del horarios_cache[cache_key]
            
        app.logger.info(f"✅ Cita agendada exitosamente: {fecha} {hora} para {telefono}")
        return jsonify({
            "status": "success",
            "message": "Cita agendada exitosamente",
            "evento_url": evento_url
        })
        
    except Exception as e:
        app.logger.error(f"Error al agendar cita: {e}")
        return jsonify({"error": "Error al procesar la cita"}), 500

@app.route('/debug-calendario', methods=["GET"])
def debug_calendario():
    """Endpoint para debug del calendario"""
    try:
        service = get_calendar_service()
        if not service:
            return jsonify({"error": "No hay servicio de calendario"})
        
        # Verificar eventos de hoy y mañana
        hoy = datetime.now().strftime("%Y-%m-%dT00:00:00-05:00")
        mañana = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT00:00:00-05:00")
        
        eventos = service.events().list(
            calendarId='primary',
            timeMin=hoy,
            timeMax=mañana,
            singleEvents=True,
            maxResults=50,
            orderBy='startTime'
        ).execute()
        
        eventos_info = []
        for evento in eventos.get('items', []):
            eventos_info.append({
                'summary': evento.get('summary', 'Sin título'),
                'start': evento['start'],
                'end': evento['end'],
                'id': evento.get('id')
            })
        
        return jsonify({
            "total_eventos": len(eventos.get('items', [])),
            "eventos": eventos_info
        })
        
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/test-calendar', methods=["GET"])
def test_calendar():
    """Probar conexión con Google Calendar"""
    try:
        service = get_calendar_service()
        if not service:
            return jsonify({"error": "No se pudo crear el servicio"})
        
        # Intentar listar calendarios
        calendars = service.calendarList().list().execute()
        
        # Probar acceso de escritura creando un evento de prueba (luego lo borramos)
        test_event = {
            'summary': 'Test Equilibra - Borrar',
            'start': {'dateTime': '2025-01-01T10:00:00-05:00', 'timeZone': 'America/Guayaquil'},
            'end': {'dateTime': '2025-01-01T11:00:00-05:00', 'timeZone': 'America/Guayaquil'},
        }
        
        created_event = service.events().insert(calendarId='primary', body=test_event).execute()
        event_id = created_event['id']
        
        # Borrar el evento de prueba
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        
        return jsonify({
            "status": "success", 
            "calendars": [cal['summary'] for cal in calendars.get('items', [])],
            "message": "✅ Conexión exitosa con Google Calendar - Permisos de lectura/escritura confirmados"
        })
        
    except HttpError as e:
        if e.resp.status == 403:
            return jsonify({"error": "❌ Error 403: Permisos insuficientes. Verifica que la cuenta de servicio tenga permisos de escritura."})
        else:
            return jsonify({"error": f"❌ Error de Google Calendar: {e}"})
    except Exception as e:
        return jsonify({"error": f"❌ Error general: {str(e)}"})

@app.route('/health')
def health_check():
    try:
        groq_ok = bool(os.getenv('GROQ_API_KEY'))
        email_ok = bool(os.getenv('EMAIL_USER')) and bool(os.getenv('EMAIL_PASSWORD'))
        
        # Probar Google Calendar
        calendar_ok = False
        calendar_message = "No configurado"
        try:
            service = get_calendar_service()
            if service:
                # Probar acceso básico
                service.calendarList().list().execute()
                calendar_ok = True
                calendar_message = "Conectado"
            else:
                calendar_message = "Error en credenciales"
        except Exception as e:
            calendar_message = f"Error: {str(e)}"
        
        return jsonify({
            'status': 'healthy' if all([groq_ok, email_ok, calendar_ok]) else 'degraded',
            'services': {
                'groq': groq_ok,
                'email': email_ok,
                'calendar': {'ok': calendar_ok, 'message': calendar_message}
            }
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# Ruta para sitemap.xml corregida
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

# Ruta para robots.txt corregida
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
    
    # En producción usar Waitress, en desarrollo usar Flask dev server
    if os.environ.get('FLASK_ENV') == 'production':
        from waitress import serve
        serve(app, host='0.0.0.0', port=port)
    else:
        app.run(host='0.0.0.0', port=port, debug=debug)