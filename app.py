from flask import Flask, render_template, request, session, redirect, url_for, jsonify
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

# ===================== CONFIGURACIÓN INICIAL =====================
load_dotenv()
env = Env()
env.read_env()

app = Flask(__name__)
app.secret_key = env.str("FLASK_SECRET_KEY")

# ✅ Forzar tamaño máximo de request (1 MB)
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  

# ✅ Configuración de seguridad de cookies
if os.environ.get('FLASK_ENV') == 'production':
    app.config.update(
        DEBUG=False,
        TESTING=False,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax"
    )
else:
    app.config['DEBUG'] = True

# Configuración de CSRF protection
csrf = CSRFProtect(app)

# Configuración de rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["1000 per day", "200 per hour"],
    storage_uri="memory://"
)

# Configuración de logging
if not os.path.exists('logs'):
    os.makedirs('logs')

handler = RotatingFileHandler('logs/app.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

# Log inicial para debug (solo en desarrollo)
if os.environ.get('FLASK_ENV') != 'production':
    app.logger.debug(f"Python version: {sys.version}")
    app.logger.debug(f"Current directory: {os.getcwd()}")
    app.logger.debug(f"Files in directory: {os.listdir('.')}")

if not os.path.exists("conversaciones"):
    os.makedirs("conversaciones")

if not os.path.exists("datos"):
    os.makedirs("datos")

# ===================== SISTEMA DE APRENDIZAJE =====================
class SistemaAprendizaje:
    def __init__(self):
        self.respuestas_efectivas = {}  # Almacena respuestas que han funcionado bien
        self.patrones_conversacion = {}  # Aprende patrones de conversación
        self.archivo_aprendizaje = "datos/aprendizaje.json"
        self.cargar_aprendizaje()
    
    def cargar_aprendizaje(self):
        """Carga los datos de aprendizaje desde archivo"""
        try:
            if os.path.exists(self.archivo_aprendizaje):
                with open(self.archivo_aprendizaje, 'r', encoding='utf-8') as f:
                    datos = json.load(f)
                    self.respuestas_efectivas = datos.get('respuestas_efectivas', {})
                    self.patrones_conversacion = datos.get('patrones_conversacion', {})
        except Exception as e:
            app.logger.error(f"Error cargando aprendizaje: {e}")
    
    def guardar_aprendizaje(self):
        """Guarda los datos de aprendizaje en archivo"""
        try:
            os.makedirs(os.path.dirname(self.archivo_aprendizaje), exist_ok=True)
            with open(self.archivo_aprendizaje, 'w', encoding='utf-8') as f:
                json.dump({
                    'respuestas_efectivas': self.respuestas_efectivas,
                    'patrones_conversacion': self.patrones_conversacion
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            app.logger.error(f"Error guardando aprendizaje: {e}")
    
    def evaluar_respuesta(self, sintoma, respuesta_usuario, respuesta_bot, engagement):
        """Evalúa qué tan efectiva fue la respuesta del bot"""
        # Calcular efectividad basada en engagement (longitud de respuesta, tiempo de interacción, etc.)
        efectividad = min(10, max(1, engagement))
        
        if sintoma not in self.respuestas_efectivas:
            self.respuestas_efectivas[sintoma] = {}
        
        # Almacenar respuesta efectiva
        if respuesta_bot not in self.respuestas_efectivas[sintoma]:
            self.respuestas_efectivas[sintoma][respuesta_bot] = {
                'efectividad_total': 0,
                'veces_usada': 0,
                'ultimo_uso': datetime.now().isoformat()
            }
        
        # Actualizar estadísticas
        self.respuestas_efectivas[sintoma][respuesta_bot]['efectividad_total'] += efectividad
        self.respuestas_efectivas[sintoma][respuesta_bot]['veces_usada'] += 1
        self.respuestas_efectivas[sintoma][respuesta_bot]['ultimo_uso'] = datetime.now().isoformat()
        
        # Guardar aprendizaje
        self.guardar_aprendizaje()
    
    def obtener_mejor_respuesta(self, sintoma, contexto):
        """Obtiene la respuesta más efectiva para un síntoma y contexto dado"""
        if sintoma in self.respuestas_efectivas and self.respuestas_efectivas[sintoma]:
            # Ordenar respuestas por efectividad
            respuestas_ordenadas = sorted(
                self.respuestas_efectivas[sintoma].items(),
                key=lambda x: x[1]['efectividad_total'] / x[1]['veces_usada'] if x[1]['veces_usada'] > 0 else 0,
                reverse=True
            )
            
            # Devolver la mejor respuesta (evitando repetir la misma muy seguido)
            for respuesta, stats in respuestas_ordenadas[:3]:  # Top 3
                ultimo_uso = datetime.fromisoformat(stats['ultimo_uso'])
                if (datetime.now() - ultimo_uso).total_seconds() > 3600:  # No repetir en 1 hora
                    return respuesta
        
        return None  # Dejar que la IA genere una nueva respuesta

# ===================== FUNCIÓN PARA GROQ API MEJORADA =====================
def generar_respuesta_llm(prompt, modelo="llama3-70b-8192"):
    """
    Envía un prompt al modelo de Groq usando el SDK oficial
    Modelos disponibles: llama3-8b-8192, llama3-70b-8192, mixtral-8x7b-32768, gemma-7b-it
    """
    try:
        # Usar el SDK oficial de Groq
        client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        
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
                    
                    EJEMPLOS DE RESPUESTAS ADECUADAS:
                    - "Entiendo que estés pasando por un momento difícil. ¿Qué has intentado para manejar esta situación?"
                    - "Es completamente normal sentirse así en estas circunstancias. ¿Te gustaría hablar más sobre qué desencadenó estos sentimientos?"
                    - "Agradezco que compartas esto conmigo. ¿Cómo ha afectado esto tu día a día?"
                    - "Parece que esto te está afectando profundamente. ¿Has considerado hablar con un profesional que pueda ayudarte de manera más personalizada?"""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=150,
            top_p=0.9,
            stream=False
        )
        
        return completion.choices[0].message.content.strip()
    
    except Exception as e:
        app.logger.error(f"Error al generar respuesta con Groq SDK: {e}")
        return None

# ===================== FUNCIONES DE UTILIDAD =====================
def sanitizar_input(texto):
    """Elimina caracteres peligrosos, escapa HTML y limita la longitud"""
    if not texto:
        return ""
    texto = escape(texto)
    texto = re.sub(r'[<>{}[\]();]', '', texto)
    return texto[:500] if len(texto) > 500 else texto

def validar_telefono(telefono):
    """Valida que el teléfono tenga el formato correcto (09xxxxxxxx)"""
    if not telefono:
        return False
    return re.match(r'^09\d{8}$', telefono) is not None

def calcular_duracion_dias(fecha_str):
    if not fecha_str:
        return 0
    try:
        fecha_inicio = datetime.strptime(fecha_str, "%Y-%m-%d")
        return (datetime.now() - fecha_inicio).days
    except ValueError:
        return 0

# ===================== DATOS DE SÍNTOMAS =====================
sintomas_disponibles = [
    "Ansiedad", "Tristeza", "Estrés", "Soledad", "Miedo", "Culpa", "Inseguridad",
    "Enojo", "Agotamiento emocional", "Falta de motivación", "Problemas de sueño",
    "Dolor corporal", "Preocupación excesiva", "Cambios de humor", "Apatía",
    "Sensación de vacío", "Pensamientos negativos", "Llanto frecuente",
    "Dificultad para concentrarse", "Desesperanza", "Tensión muscular",
    "Taquicardia", "Dificultad para respirar", "Problemas de alimentación",
    "Pensamientos intrusivos", "Problemas familiares", "Problemas de pareja"
]

# ===================== RESPUESTAS POR SÍNTOMA =====================
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
    "Estrés": [
        "¿Notas si el estrés aparece más en ciertos momentos del día?",
        "A veces, solo detenerse y respirar ya es una forma de cuidarse.",
        "¿Te estás exigiendo demasiado últimamente?",
        "El estrés también habla de tus límites. ¿Puedes identificar alguno que fue cruzado?",
        "Probar técnicas breves como estiramientos, música relajante o caminar puede ayudar.",
        "¿Te has permitido no ser productivo un día sin sentir culpa?",
        "Es posible organizar el caos en partes pequeñas. ¿Te ayudo a descomponerlo?",
        "¿Tu cuerpo ha mostrado señales físicas de ese estrés (dolores, rigidez)?",
        "Darte un espacio para ti es un acto necesario, no egoísta.",
        "Tomarte pausas no es perder tiempo; es cuidar tu salud emocional."
    ],
    "Soledad": [
        "La soledad puede sentirse como un vacío difícil de explicar. Gracias por compartirlo.",
        "¿Qué tipo de compañía sientes que necesitas: emocional, física, espiritual?",
        "¿Hay alguna actividad que te conecte contigo y te haga sentir menos solo?",
        "¿Has considerado escribirle a alguien con quien no hablas hace tiempo?",
        "Conectar con otros lleva tiempo, and está bien tomarse ese proceso con calma.",
        "¿Te gustaría imaginar cómo sería un vínculo que te dé contención?",
        "A veces estar acompañado por alguien no significa dejar de sentir soledad. ¿Lo has sentido?",
        "¿Qué podrías hacer hoy que te haga sentir parte de algo, aunque sea pequeño?",
        "¿Hay alguna comunidad o espacio que quisieras explorar?",
        "Recuerda que mereces sentirte valorado y escuchado."
    ],
    "Miedo": [
        "El miedo es una emoción natural que nos protege, pero no debe paralizarnos.",
        "¿Puedes identificar qué te provoca miedo exactamente?",
        "Hablar de tus miedos puede ayudarte to entenderlos mejor.",
        "¿Cómo reaccionas cuando el miedo aparece?",
        "Enfrentar poco a poco esos miedos puede disminuir su poder.",
        "¿Has probado técnicas de relajación cuando sientes miedo?",
        "Compartir lo que sientes puede aliviar la carga emocional.",
        "¿Sientes que el miedo limita tu vida o tus decisiones?",
        "La valentía no es ausencia de miedo, sino actuar a pesar de él.",
        "Si el miedo persiste, buscar ayuda profesional es una buena opción."
    ],
    "Culpa": [
        "Sentir culpa puede ser agotador. ¿Qué parte de ti necesita ser perdonada?",
        "¿Eres igual de duro contigo que lo serías con alguien que amas?",
        "¿La culpa viene de una expectativa tuya or de los demás?",
        "Podemos aprender de lo que pasó sin cargarlo como un castigo eterno.",
        "Todos cometemos errores. La clave está en lo que haces con eso ahora.",
        "¿Hay algo que puedas hacer para reparar o aliviar esa carga?",
        "A veces la culpa no es real, sino impuesta. ¿De quién es esa voz interna?",
        "Eres humano. Equivocarte no te hace menos valioso.",
        "¿Qué le dirías a un amigo if estuviera en tu lugar?",
        "Reconocer lo que sientes es el primer paso hacia la liberación emocional."
    ],
    "Inseguridad": [
        "La inseguridad puede afectar muchas áreas de tu vida.",
        "¿En qué situaciones te sientes más inseguro?",
        "Hablar de tus inseguridades es un buen paso para superarlas.",
        "¿Qué cualidades positivas reconoces en ti mismo?",
        "Reconocer tus fortalezas puede ayudarte a aumentar tu confianza.",
        "¿Has probado ejercicios para mejorar tu autoestima?",
        "¿Cómo afecta la inseguridad tus relaciones con otros?",
        "Es normal sentir inseguridad, pero no define quién eres.",
        "¿Tienes alguien de confianza para hablar sobre esto?",
        "Buscar apoyo puede ayudarte a fortalecer tu confianza.",
    ],
    "Enojo": [
        "El enojo es una emoción válida, es bueno expresarlo.",
        "¿Qué situaciones suelen generar tu enojo?",
        "¿Cómo sueles manejar tu enojo cuando aparece?",
        "Hablar sobre lo que te molesta puede ayudarte a calmarte.",
        "¿Has probado técnicas para controlar la ira o relajarte?",
        "Reconocer tu enojo es el primer paso para gestionarlo.",
        "¿Cómo afecta el enojo tus relaciones personales?",
        "¿Tienes alguien con quien puedas hablar cuando estás enojado?",
        "Expresar el enojo de forma saludable es importante.",
        "¿Qué cosas te ayudan a calmarte cuando estás molesto?",
        "¿Has notado si el enojo se relaciona con otras emociones?",
        "Buscar apoyo puede facilitar manejar mejor el enojo.",
        "¿Quieres contarme alguna experiencia reciente que te haya enojado?",
        "Practicar la empatía puede ayudarte a manejar el enojo.",
        "Si el enojo es muy frecuente, considera hablar con un especialista."
    ],
    "Agotamiento emocional": [
        "El agotamiento emocional puede afectar tu energía y ánimo.",
        "¿Qué cosas te están causando más cansancio emocional?",
        "Es importante que te des tiempo para descansar y recargar.",
        "Hablar de cómo te sientes puede aliviar parte del agotamiento.",
        "¿Has intentado actividades que te ayuden a relajarte?",
        "Reconocer el agotamiento es clave para cuidarte mejor.",
        "¿Sientes que el agotamiento afecta tu vida diaria?",
        "¿Tienes apoyo para compartir lo que estás viviendo?",
        "El autocuidado es fundamental para superar el agotamiento.",
        "¿Qué cosas te gustaría cambiar para sentirte con más energía?",
        "Es válido pedir ayuda cuando te sientes muy cansado/a.",
        "¿Quieres contarme cómo has estado manejando este cansancio?",
        "Tomar pausas durante el día puede ayudarte a recuperar energías.",
        "Recuerda que cuidar de ti es una prioridad.",
        "Si el agotamiento persiste, considera consultar con un profesional."
    ],
    "Falta de motivación": [
        "La falta de motivación puede ser difícil, pero es temporal.",
        "¿Qué cosas te gustaría lograr si tuvieras más energía?",
        "Hablar de tus sentimientos puede ayudarte a encontrar motivación.",
        "¿Has identificado qué te quita las ganas de hacer cosas?",
        "Pequeños pasos pueden ayudarte a recuperar la motivación.",
        "¿Tienes alguien que te apoye en tus metas?",
        "Reconocer la falta de motivación es el primer paso para cambiar.",
        "¿Qué actividades solías disfrutar y ahora te cuestan más?",
        "Es normal tener altibajos en la motivación, sé paciente.",
        "¿Quieres contarme cómo te sientes al respecto?",
        "Buscar apoyo puede facilitar que recuperes el interés.",
        "¿Hay obstáculos que te impiden avanzar?",
        "Celebrar pequeños logros puede aumentar tu motivación.",
        "¿Has probado cambiar tu rutina para sentirte mejor?",
        "Si la falta de motivación es persistente, considera ayuda profesional."
    ],
    "Problemas de sueño": [
        "Dormir bien es fundamental para tu bienestar general.",
        "¿Qué dificultades tienes para conciliar o mantener el sueño?",
        "Crear una rutina antes de dormir puede ayudarte a descansar mejor.",
        "Evitar pantallas antes de dormir puede mejorar la calidad del sueño.",
        "¿Has probado técnicas de relajación para dormir mejor?",
        "Reconocer el problema es importante para buscar soluciones.",
        "¿Sientes que el sueño insuficiente afecta tu ánimo o concentración?",
        "¿Tienes hábitos que podrían estar interfiriendo con tu descanso?",
        "Hablar de tus preocupaciones puede facilitar dormir mejor.",
        "¿Quieres contarme cómo es tu rutina de sueño actual?",
        "El ejercicio regular puede ayudar a mejorar el sueño.",
        "Evitar cafeína o comidas pesadas antes de dormir es recomendable.",
        "¿Has tenido episodios de insomnio prolongados?",
        "Si los problemas de sueño persisten, un especialista puede ayudar.",
        "Cuidar el ambiente donde duermes es clave para un buen descanso."
    ],
    "Dolor corporal": [
        "El dolor puede afectar mucho tu calidad de vida, es importante escucharlo.",
        "¿Dónde sientes más el dolor y cómo describirías su intensidad?",
        "Hablar sobre el dolor puede ayudarte a entenderlo mejor.",
        "¿Has probado técnicas de relajación or estiramientos suaves?",
        "El estrés puede influir en la percepción del dolor.",
        "¿Has consultado a un profesional sobre este dolor?",
        "Cuidar tu postura puede ayudar a disminuir molestias físicas.",
        "¿El dolor afecta tus actividades diarias?",
        "¿Sientes que hay momentos del día en que el dolor empeora?",
        "Es válido buscar ayuda médica y psicológica para el dolor crónico.",
        "¿Quieres contarme cómo te afecta emocionalmente el dolor?",
        "La conexión cuerpo-mente es importante para el bienestar general.",
        "¿Has probado terapias complementarias, como masajes o yoga?",
        "Escuchar a tu cuerpo es clave para cuidarte mejor.",
        "Si el dolor es constante, no dudes en buscar apoyo especializado."
    ],
    "Preocupación excesiva": [
        "Preocuparse es normal, pero en exceso puede afectar tu vida.",
        "¿Qué pensamientos recurrentes te generan más preocupación?",
        "Hablar de tus preocupaciones puede aliviar su peso.",
        "¿Has probado técnicas para distraer tu mente o relajarte?",
        "Reconcer la preocupación es el primer paso para manejarla.",
        "¿Sientes que la preocupación afecta tu sueño o ánimo?",
        "¿Tienes alguien con quien puedas compartir lo que te preocupa?",
        "Aprender a diferenciar lo que puedes controlar ayuda a reducir el estrés.",
        "¿Quieres contarme qué te gustaría cambiar respecto a tus preocupaciones?",
        "Buscar apoyo puede facilitar encontrar soluciones efectivas.",
        "¿Has intentado escribir tus pensamientos para entenderlos mejor?",
        "La práctica de mindfulness puede ayudar a reducir la preocupación.",
        "¿Sientes que la preocupación interfiere en tus actividades diarias?",
        "Es válido pedir ayuda si las preocupaciones son muy intensas.",
        "Recuerda que tu bienestar es importante y mereces cuidado."
    ],
    "Cambios de humor": [
        "Los cambios de humor pueden ser difíciles de manejar.",
        "¿Puedes identificar qué situaciones disparan esos cambios?",
        "Hablar de tus emociones puede ayudarte a entenderlas mejor.",
        "¿Has notado patrones en tus cambios de humor?",
        "Reconocer tus sentimientos es un paso para gestionarlos.",
        "¿Tienes alguien con quien puedas compartir cómo te sientes?",
        "¿Cómo afectan esos cambios tu vida diaria y relaciones?",
        "Es importante cuidar de tu salud emocional constantemente.",
        "¿Quieres contarme cómo te sientes en los momentos más estables?",
        "Buscar apoyo puede facilitar manejar los cambios emocionales.",       
    ],
    "Apatía": [
        "Sentir apatía puede hacer que todo parezca sin sentido.",
        "¿Quieres contarme qué cosas te generan menos interés ahora?",
        "Hablar de lo que sientes puede ayudarte a reconectar contigo.",
        "¿Has notado si la apatía está relacionada con otras emociones?",
        "Reconocerla es importante para buscar formas de superarla.",
        "¿Tienes alguien con quien puedas compartir tus sentimientos?",
        "Pequeños cambios en tu rutina pueden ayudar a mejorar.",
        "¿Qué cosas te gustaría recuperar o volver a disfrutar?",
        "Es normal tener momentos bajos, sé paciente contigo mismo.",
        "¿Quieres contarme cómo te sientes en general últimamente?",
        "Buscar apoyo puede facilitar que recuperes energía e interés.",
        "¿Has probado actividades nuevas o diferentes para motivarte?",
        "Recuerda que mereces cuidado y atención a tus emociones.",
        "Si la apatía persiste, considera hablar con un profesional.",
        "Tu bienestar es importante and hay caminos para mejorar."
    ],
    "Sensación de vacío": [
        "Sentir vacío puede ser muy desconcertante, gracias por compartir.",
        "¿Quieres contarme cuándo empezaste a sentir ese vacío?",
        "Hablar sobre ello puede ayudarte a entender mejor tus emociones.",
        "¿Hay momentos en que ese vacío se hace más presente?",
        "Reconocer este sentimiento es un primer paso para manejarlo.",
        "¿Tienes alguien con quien puedas compartir cómo te sientes?",
        "A veces, el vacío puede indicar que necesitas cambios en tu vida.",
        "¿Qué cosas te hacían sentir pleno o feliz antes?",
        "Es válido buscar ayuda para reconectar contigo mismo.",
        "¿Quieres contarme cómo es tu día a día con esta sensación?",
        "Explorar tus emociones puede ayudarte a llenar ese vacío.",
        "Recuerda que mereces sentirte bien y en paz interiormente.",
        "¿Has probado actividades que te conecten con tus intereses?",
        "Si este sentimiento persiste, un especialista puede apoyarte.",
        "Estoy aquí para escucharte y acompañarte en este proceso."
    ],
    "Pensamientos negativos": [
        "Los pensamientos negativos pueden ser muy pesados.",
        "¿Puedes contarme qué tipo de pensamientos recurrentes tienes?",
        "Hablar sobre ellos puede ayudarte a liberarte un poco.",
        "Reconocer estos pensamientos es el primer paso para manejarlos.",
        "¿Sientes que afectan cómo te ves a ti mismo o a los demás?",
        "¿Has probado técnicas para reemplazarlos por otros más positivos?",
        "Es normal tener pensamientos negativos, pero no definen quién eres.",
        "¿Tienes alguien con quien puedas compartir tus inquietudes?",
        "Buscar apoyo puede facilitar encontrar formas de manejarlos.",
        "¿Quieres contarme cuándo suelen aparecer esos pensamientos?",
        "Practicar la autocompasión es importante para tu bienestar.",
        "¿Cómo afectan esos pensamientos tu vida diaria?",
        "Si los pensamientos son muy intensos, considera ayuda profesional.",
        "Recuerda que mereces paz mental y emocional.",
        "Estoy aquí para escucharte y apoyarte en este camino."
    ],
    "Llanto frecuente": [
        "Llorar es una forma natural de liberar emociones contenidas.",
        "¿Sientes que lloras sin saber exactamente por qué?",
        "No estás solo/a. Muchas personas pasan por esto más seguido de lo que imaginas.",
        "¿Qué suele pasar antes de que sientas ganas de llorar?",
        "Tu llanto también es una voz que pide ser escuchada.",
        "¿Hay algo que estés conteniendo desde hace tiempo?",
        "¿Después de llorar sientes alivio o más angustia?",
        "No te juzgues por expresar tu dolor. Es válido y humano.",
        "¿Has tenido un espacio seguro donde simplemente puedas llorar y ser escuchado?",
        "Tus lágrimas tienen un motivo. ¿Te gustaría explorar cuál es?"
    ],
    "Dificultad para concentrarse": [
        "La concentración puede verse afectada por muchos factores.",
        "¿Quieres contarme cuándo notas más esta dificultad?",
        "Hablar de lo que te distrae puede ayudarte a mejorar tu foco.",
        "Reconocer este problema es importante para buscar soluciones.",
        "¿Sientes que tu mente está muy dispersa o cansada?",
        "¿Has probado técnicas como pausas cortas o ambientes tranquilos?",
        "El estrés y la ansiedad pueden influir en la concentración.",
        "¿Tienes alguien con quien puedas compartir cómo te sientes?",
        "Buscar apoyo puede facilitar que mejores tu atención.",
        "¿Quieres contarme cómo afecta esta dificultad tu día a día?",
        "Practicar ejercicios mentales puede ayudarte a fortalecer el foco.",
        "¿Has intentado organizar tus tareas para facilitar la concentración?",
        "Si esta dificultad es persistente, considera ayuda profesional.",
        "Recuerda que mereces sentirte capaz y enfocado.",
        "Estoy aquí para escucharte y apoyarte en este proceso."
    ],
    "Desesperanza": [
        "Sentir desesperanza es muy difícil, gracias por compartir.",
        "¿Quieres contarme qué te hace sentir así últimamente?",
        "Hablar sobre ello puede ayudarte a encontrar luz en la oscuridad.",
        "Reconocer esos sentimientos es el primer paso para salir adelante.",
        "¿Tienes alguien con quien puedas compartir lo que sientes?",
        "Es válido pedir ayuda cuando sientes que la esperanza falta.",
        "¿Qué cosas te han dado un poco de alivio en momentos difíciles?",
        "Recuerda que mereces apoyo y cuidado en estos momentos.",
        "¿Quieres contarme cómo te imaginas un futuro mejor?",
        "Buscar ayuda profesional puede ser muy beneficioso ahora.",
        "¿Has intentado actividades que te ayuden a sentir esperanza?",
        "No estás solo/a, y hay caminos para sentirte mejor.",
        "¿Quieres que te comparta recursos or estrategias para esto?",
        "Estoy aquí para escucharte y acompañarte siempre.",
        "La esperanza puede volver, paso a paso y con apoyo."
    ],
    "Tensión muscular": [
        "La tensión muscular puede ser síntoma de estrés o ansiedad.",
        "¿En qué partes de tu cuerpo sientes más tensión?",
        "Probar estiramientos suaves puede ayudarte to aliviar la tensión.",
        "¿Has intentado técnicas de relajación o respiración profunda?",
        "Hablar de tu estado puede ayudarte a identificar causas.",
        "¿Sientes que la tensión afecta tu movilidad or bienestar?",
        "El descanso y una buena postura son importantes para el cuerpo.",
        "¿Tienes alguien con quien puedas compartir cómo te sientes?",
        "Buscar ayuda puede facilitar aliviar la tensión muscular.",
        "¿Quieres contarme cuándo notas más esa tensión?",
        "La conexión mente-cuerpo es clave para tu bienestar.",
        "Considera actividades como yoga o masajes para relajarte.",
        "Si la tensión persiste, un profesional puede ayudarte.",
        "Recuerda que cuidar de tu cuerpo es parte del autocuidado.",
        "Estoy aquí para apoyarte y escucharte siempre."
    ],
    "Taquicardia": [
        "La taquicardia puede ser alarmante, es bueno que hables de ello.",
        "¿Cuándo has notado que se acelera tu corazón?",
        "¿Sientes que la taquicardia está relacionada con el estrés o ansiedad?",
        "Es importante que consultes con un médico para evaluar tu salud.",
        "¿Has probado técnicas de respiración para calmarte?",
        "Hablar de lo que sientes puede ayudarte a manejar la ansiedad.",
        "¿Sientes otros síntomas junto con la taquicardia?",
        "¿Tienes alguien con quien puedas compartir estas experiencias?",
        "Buscar apoyo profesional es clave para cuidar tu salud.",
        "¿Quieres contarme cómo te sientes cuando ocurre esto?",
        "La información y la atención médica son fundamentales.",
        "Recuerda que mereces cuidado y atención constante.",
        "¿Has evitado situaciones que crees que la provocan?",
        "Si la taquicardia persiste, no dudes en buscar ayuda urgente.",
        "Estoy aquí para escucharte y acompañarte."
    ],
    "Dificultad para respirar": [
        "La dificultad para respirar puede ser muy angustiante.",
        "¿Cuándo sueles sentir que te falta el aire?",
        "Probar respiraciones lentas y profundas puede ayudar momentáneamente.",
        "Es fundamental que consultes con un profesional de salud.",
        "¿Sientes que la dificultad está relacionada con ansiedad o estrés?",
        "Hablar de lo que experimentas puede ayudarte a manejarlo.",
        "¿Tienes alguien con quien puedas compartir estas sensaciones?",
        "Buscar ayuda médica es muy importante en estos casos.",
        "¿Quieres contarme cómo te afecta esta dificultad en tu vida?",
        "Recuerda que tu salud es prioridad y merece atención inmediata.",
        "¿Has evitado situaciones que aumentan la dificultad para respirar?",
        "Mantener la calma puede ayudarte a controlar la respiración.",
        "If la dificultad es constante, acude a un especialista pronto.",
        "Estoy aquí para escucharte y apoyarte.",
        "No estás solo/a, y hay ayuda para ti."
    ],
    "Problemas de alimentación": [
        "Los problemas de alimentación pueden afectar tu salud integral.",
        "¿Quieres contarme qué dificultades estás experimentando?",
        "Hablar de tus hábitos puede ayudarte a entender mejor la situación.",
        "Reconocer el problema es el primer paso para buscar soluciones.",
        "¿Sientes que tu relación con la comida ha cambiado?",
        "¿Has notado si comes menos, más o de forma irregular?",
        "Buscar apoyo puede facilitar que mejores tus hábitos alimenticios.",
        "¿Tienes alguien con quien puedas compartir tus sentimientos?",
        "El cuidado nutricional es importante para tu bienestar general.",
        "¿Quieres contarme cómo te sientes emocionalmente respecto a la comida?",
        "Pequeños cambios pueden hacer una gran diferencia.",
        "Si los problemas persisten, considera ayuda profesional.",
        "Recuerda que mereces cuidar tu cuerpo y mente.",
        "Estoy aquí para escucharte y acompañarte en esto.",
        "Buscar ayuda es un acto de valentía y cuidado personal."
    ],
    "Pensamientos intrusivos": [
        "Los pensamientos intrusivos pueden ser muy molestos.",
        "¿Quieres contarme qué tipo de pensamientos te molestan?",
        "Hablar sobre ellos puede ayudarte a reducir su impacto.",
        "Reconocerlos es un paso para poder manejarlos mejor.",
        "¿Sientes que afectan tu día a día o tu bienestar?",
        "¿Has probado técnicas para distraer tu mente o relajarte?",
        "Buscar apoyo puede facilitar que encuentres estrategias útiles.",
        "¿Tienes alguien con quien puedas compartir estas experiencias?",
        "¿Quieres contarme cuándo suelen aparecer estos pensamientos?",
        "Practicar mindfulness puede ayudarte a observar sin juzgar.",
        "Es normal tener pensamientos intrusivos, no te defines por ellos.",
        "Si son muy intensos, considera ayuda profesional.",
        "Recuerda que mereces paz mental y emocional.",
        "Estoy aquí para escucharte y apoyarte en este camino.",
        "Hablar y compartir puede ser parte de tu sanación."
    ],
    "Problemas familiares": [
        "Las relaciones familiares pueden ser complejas, es válido sentirte así.",
        "¿Quieres contarme qué tipo de conflicto estás viviendo en casa?",
        "A veces, expresar lo que sientes puede aliviar tensiones con tus seres queridos.",
        "¿Sientes que te entienden en tu entorno familiar?",
        "Hablar de los problemas familiares es un paso para encontrar soluciones.",
        "¿Qué te gustaría que cambiara en tu relación con tu familia?",
        "Recuerda que cuidar tu bienestar emocional también es importante en medio de conflictos.",
        "¿Tienes algún familiar con quien puedas hablar con confianza?",
        "Establecer límites sanos puede ayudarte a sentirte mejor.",
        "Si el ambiente familiar te genera malestar constante, es válido buscar apoyo externo.",
        "¿Has intentado dialogar con alguien de tu familia recientemente?",
        "No estás solo/a, muchos pasamos por conflictos similares.",
        "¿Quieres contarme cómo ha sido tu experiencia en tu hogar últimamente?",
        "Reconocer el problema es un paso importante para tu sanación.",
        "Si sientes que no puedes manejarlo solo/a, un profesional puede ayudarte."
    ],
    "Problemas de pareja": [
        "Las relaciones tienen altibajos, es válido buscar apoyo.",
        "¿Quieres contarme qué pasa con tu pareja?",
        "Expresar tus emociones puede ayudarte a entender mejor.",
        "¿Sientes que la relación te afecta emocionalmente?",
        "Los conflictos son comunes, pero mereces sentirte escuchado.",
        "¿Qué te gustaría mejorar en la relación?",
        "El respeto mutuo es clave.",
        "¿Tienes alguien para hablar cuando se complica la relación?",
        "Pedir ayuda es sano cuando cargas mucho emocionalmente.",
        "Hablar con un profesional puede aclarar tus sentimientos."
    ]
}

# ===================== SISTEMA CONVERSACIONAL MEJORADO CON APRENDIZAJE =====================
class SistemaConversacional:
    def __init__(self):
        self.historial = []
        self.contador_interacciones = 0
        self.contexto_actual = None
        self.sistema_aprendizaje = SistemaAprendizaje()
        self.engagement_actual = 5  # Valor por defecto de engagement

    def to_dict(self):
        """Convierte el objeto a un diccionario para serialización"""
        return {
            'historial': self.historial,
            'contador_interacciones': self.contador_interacciones,
            'contexto_actual': self.contexto_actual,
            'engagement_actual': self.engagement_actual
        }
    
    @classmethod
    def from_dict(cls, data):
        """Recrea el objeto desde un diccionario"""
        instance = cls()
        instance.historial = data.get('historial', [])
        instance.contador_interacciones = data.get('contador_interacciones', 0)
        instance.contexto_actual = data.get('contexto_actual', None)
        instance.engagement_actual = data.get('engagement_actual', 5)
        return instance

    def obtener_respuesta_predefinida(self, sintoma):
        """Obtiene una respuesta predefinida para el síntoma específico"""
        if sintoma in respuestas_por_sintoma:
            return random.choice(respuestas_por_sintoma[sintoma])
        
        # Respuestas genéricas empáticas como fallback
        respuestas_genericas = [
            "Entiendo que esto puede ser difícil de manejar. ¿Quieres contarme más sobre cómo te sientes?",
            "Aprecio que compartas esto conmigo. ¿Hay algo específico que haya desencadenado estos sentimientos?",
            "Es completamente normal sentirse así a veces. ¿Cómo ha afectado esto tu día a día?",
            "Lamento escuchar que estás pasando por esto. ¿Has intentado alguna estrategia para manejar la situación?",
            "Gracias por confiar en mí para hablar de esto. ¿Qué es lo que más te preocupa en este momento?"
        ]
        return random.choice(respuestas_genericas)

    def obtener_respuesta_ia(self, sintoma, user_input):
        """Intenta obtener respuesta de la IA con mejor manejo de errores"""
        try:
            # Preparar prompt contextualizado
            contexto = f"""
            El usuario está experimentando: {sintoma}. 
            Historial reciente: {str(self.historial[-2:]) if len(self.historial) > 2 else 'Primera interacción'}
            Último mensaje del usuario: "{user_input}"
            
            Por favor, responde de manera empática y profesional.
            """
            
            respuesta = generar_respuesta_llm(contexto, modelo="llama3-70b-8192")
            
            # Si falla el modelo principal, intentar con alternativo
            if not respuesta or len(respuesta) < 10:
                respuesta = generar_respuesta_llm(contexto, modelo="mixtral-8x7b-32768")
            
            # Verificar si la respuesta es válida
            if respuesta and len(respuesta) > 10:
                return respuesta
        except Exception as e:
            app.logger.error(f"Error al obtener respuesta de IA: {e}")
        
        # Fallback a respuesta predefinida si hay error
        return self.obtener_respuesta_predefinida(sintoma)

    def obtener_respuesta(self, sintoma, user_input):
        # 1. Filtro de seguridad (suicidio, autolesión, etc.)
        palabras_crisis = ["suicidio", "autolesión", "autoflagelo", "matarme", "no quiero vivir", 
                          "acabar con todo", "no vale la pena", "sin esperanza", "quiero morir"]
        
        input_lower = user_input.lower()
        if any(palabra in input_lower for palabra in palabras_crisis):
            return "⚠️ Veo que estás pasando por un momento muy difícil. Es importante que hables con un profesional de inmediato. Por favor, comunícate con la línea de crisis al 911 o con tu psicólogo de confianza."

        # 2. Verificar si el usuario solicita cita explícitamente
        palabras_cita = ["cita", "consulta", "profesional", "psicólogo", "psicologo", "terapia", "agendar"]
        if any(palabra in input_lower for palabra in palabras_cita):
            return "Entiendo que te gustaría hablar con un profesional. ¿Te gustaría que te ayude a agendar una cita presencial con un psicólogo?"

        # 3. Intentar con respuesta aprendida primero
        respuesta_aprendida = self.sistema_aprendizaje.obtener_mejor_respuesta(sintoma, user_input)
        if respuesta_aprendida:
            app.logger.info(f"Usando respuesta aprendida para {sintoma}")
            self.contador_interacciones += 1
            return respuesta_aprendida

        # 4. Si no hay respuesta aprendida, usar IA
        respuesta_ia = self.obtener_respuesta_ia(sintoma, user_input)
        self.contador_interacciones += 1
        
        # 5. Aprender de esta interacción
        self.aprender_de_interaccion(sintoma, user_input, respuesta_ia)
        
        # 6. Si después de algunas interacciones, sugerir cita suavemente
        if self.contador_interacciones >= 3 and not any(palabra in respuesta_ia.lower() for palabra in palabras_cita):
            respuesta_ia += " ¿Has considerado la posibilidad de hablar con un psicólogo profesional? Podría ofrecerte un apoyo más personalizado."
        
        return respuesta_ia

    def aprender_de_interaccion(self, sintoma, user_input, respuesta_bot):
        """Aprende de la interacción actual"""
        # Calcular engagement basado en longitud de respuesta del usuario
        engagement = min(10, len(user_input) / 10)  # Más largo = más engagement
        
        # Añadir al sistema de aprendizaje
        self.sistema_aprendizaje.evaluar_respuesta(sintoma, user_input, respuesta_bot, engagement)
        
        # Aprender patrones de conversación
        self.aprender_patrones(user_input, respuesta_bot)

    def aprender_patrones(self, user_input, respuesta_bot):
        """Aprende patrones de conversación comunes"""
        palabras_usuario = set(user_input.lower().split())
        palabras_bot = set(respuesta_bot.lower().split())
        
        # Simplificar para ejemplo - en la práctica usarías técnicas NLP más avanzadas
        for palabra in palabras_usuario:
            if palabra not in self.sistema_aprendizaje.patrones_conversacion:
                self.sistema_aprendizaje.patrones_conversacion[palabra] = {}
            
            for palabra_bot in palabras_bot:
                if palabra_bot not in self.sistema_aprendizaje.patrones_conversacion[palabra]:
                    self.sistema_aprendizaje.patrones_conversacion[palabra][palabra_bot] = 0
                self.sistema_aprendizaje.patrones_conversacion[palabra][palabra_bot] += 1
        
        self.sistema_aprendizaje.guardar_aprendizaje()

    def agregar_interaccion(self, tipo, mensaje, sintoma=None):
        interaccion = {
            'tipo': tipo,
            'mensaje': mensaje,
            'sintoma': sintoma,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        }
        self.historial.append(interaccion)
        
        # Si es una respuesta del usuario, actualizar engagement
        if tipo == 'user' and len(self.historial) > 1:
            ultima_respuesta_bot = self.historial[-2] if self.historial[-2]['tipo'] == 'bot' else None
            if ultima_respuesta_bot:
                # Calcular engagement basado en longitud de respuesta
                self.engagement_actual = min(10, len(mensaje) / 15)
                
                # Aprender de esta interacción
                self.aprender_de_interaccion(
                    ultima_respuesta_bot['sintoma'] or "general",
                    mensaje,
                    ultima_respuesta_bot['mensaje']
                )

# ===================== FUNCIONES DE CALENDARIO =====================
@lru_cache(maxsize=128)
def get_calendar_service():
    try:
        creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        app.logger.error(f"Error al obtener servicio de calendario: {e}")
        return None

def crear_evento_calendar(fecha, hora, telefono, sintoma):
    try:
        service = get_calendar_service()
        if not service:
            return None
            
        event = {
            'summary': f'Cita psicológica - {sintoma}',
            'description': f'Teléfono: {telefono}\nSíntoma: {sintoma}',
            'start': {
                'dateTime': f"{fecha}T{hora}:00-05:00",
                'timeZone': 'America/Guayaquil',
            },
            'end': {
                'dateTime': f"{fecha}T{int(hora.split(':')[0])+1}:00:00-05:00",
                'timeZone': 'America/Guayaquil',
            },
        }
        event = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()
        
        return event.get('htmlLink')
    except HttpError as error:
        app.logger.error(f"Error al crear evento: {error}")
        return None
    except Exception as e:
        app.logger.error(f"Error inesperado al crear evento: {e}")
        return None

# ===================== FUNCIÓN DE CORREO =====================
def enviar_correo_confirmacion(destinatario, fecha, hora, telefono, sintoma):
    remitente = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")
    
    if not remitente or not password:
        app.logger.error("Credenciales de email no configuradas")
        return False
    
    mensaje = MIMEMultipart()
    mensaje['From'] = remitente
    mensaje['To'] = destinatario
    mensaje['Subject'] = f"Nueva cita presencial agendada - {fecha} {hora}"
    
    cuerpo = f"""
    📅 Nueva cita presencial agendada:
    Fecha: {fecha}
    Hora: {hora}
    Teléfono: {telefono}
    Síntoma principal: {sintoma}
    
    El paciente será contactado para confirmar cita.
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

# ===================== LIMPIADOR AUTOMÁTICO DE DATOS =====================
def limpiar_datos_aprendizaje():
    """Limpia periódicamente datos de aprendizaje antiguos o poco útiles"""
    try:
        # Esta función se ejecutará en un hilo separado
        while True:
            time.sleep(24 * 60 * 60)  # 24 horas
            
            # Cargar datos actuales
            sistema_aprendizaje = SistemaAprendizaje()
            
            for sintoma in list(sistema_aprendizaje.respuestas_efectivas.keys()):
                for respuesta in list(sistema_aprendizaje.respuestas_efectivas[sintoma].keys()):
                    stats = sistema_aprendizaje.respuestas_efectivas[sintoma][respuesta]
                    ultimo_uso = datetime.fromisoformat(stats['ultimo_uso'])
                    
                    # Eliminar respuestas muy antiguas o poco efectivas
                    if (datetime.now() - ultimo_uso).days > 30 or stats['veces_usada'] < 2:
                        del sistema_aprendizaje.respuestas_efectivas[sintoma][respuesta]
                
                # Eliminar síntomas sin respuestas
                if not sistema_aprendizaje.respuestas_efectivas[sintoma]:
                    del sistema_aprendizaje.respuestas_efectivas[sintoma]
            
            sistema_aprendizaje.guardar_aprendizaje()
            app.logger.info("Limpieza automática de datos de aprendizaje completada")
            
    except Exception as e:
        app.logger.error(f"Error limpiando datos de aprendizaje: {e}")

# Iniciar hilo de limpieza en segundo plano (solo en producción)
if os.environ.get('FLASK_ENV') == 'production':
    hilo_limpieza = threading.Thread(target=limpiar_datos_aprendizaje, daemon=True)
    hilo_limpieza.start()

# ===================== RUTAS PRINCIPALES =====================
@app.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")
def index():
    # ✅ Asegurar que fechas_validas siempre exista en la sesión
    if "fechas_validas" not in session:
        session["fechas_validas"] = {
            'hoy': datetime.now().strftime('%Y-%m-%d'),
            'min_cita': datetime.now().strftime('%Y-%m-%d'),
            'max_cita': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'min_sintoma': (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d'),
            'max_sintoma': datetime.now().strftime('%Y-%m-%d')
        }

    # ✅ Inicializar o recuperar la conversación
    if "conversacion_data" not in session:
        conversacion = SistemaConversacional()
        session.update({
            "estado": "inicio",
            "sintoma_actual": None,
            "conversacion_data": conversacion.to_dict()
        })
    else:
        # Recuperar la conversación desde el diccionario
        conversacion = SistemaConversacional.from_dict(session["conversacion_data"])

    if request.method == "POST":
        estado_actual = session["estado"]

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

        elif estado_actual == "profundizacion":
            if user_input := sanitizar_input(request.form.get("user_input", "").strip()):
                conversacion.agregar_interaccion('user', user_input, session["sintoma_actual"])
                
                # Verificar si el usuario solicita cita explícitamente
                if any(palabra in user_input.lower() for palabra in ["cita", "consulta", "profesional", "psicólogo", "psicologo", "terapia", "agendar"]):
                    session["estado"] = "derivacion"
                    conversacion.agregar_interaccion('bot', "Entiendo que te gustaría hablar con un profesional. ¿Te gustaría que te ayude a agendar una cita presencial?", session["sintoma_actual"])
                else:
                    respuesta = conversacion.obtener_respuesta(session["sintoma_actual"], user_input)
                    conversacion.agregar_interaccion('bot', respuesta, session["sintoma_actual"])

        elif estado_actual == "derivacion":
            if user_input := sanitizar_input(request.form.get("user_input", "").strip()):
                conversacion.agregar_interaccion('user', user_input, session["sintoma_actual"])
                if any(palabra in user_input.lower() for palabra in ["sí", "si", "quiero", "agendar", "cita", "ok", "vale", "por favor"]):
                    session["estado"] = "agendar_cita"
                    mensaje = (
                        "Excelente decisión. Por favor completa los datos para tu cita presencial:\n\n"
                        "📅 Selecciona una fecha disponible\n"
                        "⏰ Elige un horario que te convenga\n"
                        "📱 Ingresa tu número de teléfono para contactarte"
                    )
                    conversacion.agregar_interaccion('bot', mensaje, session["sintoma_actual"])
                else:
                    session["estado"] = "profundizacion"
                    respuesta = conversacion.obtener_respuesta(session["sintoma_actual"], user_input)
                    conversacion.agregar_interaccion('bot', respuesta, session["sintoma_actual"])

        elif estado_actual == "agendar_cita":
            if fecha := request.form.get("fecha_cita"):
                telefono = request.form.get("telefono", "").strip()

                if not validar_telefono(telefono):
                    conversacion.agregar_interaccion('bot', "⚠️ El teléfono debe comenzar con 09 y tener 10 dígitos numéricos. Por favor, ingrésalo de nuevo.", None)
                    session["conversacion_data"] = conversacion.to_dict()
                    return redirect(url_for("index"))

                cita = {
                    "fecha": fecha,
                    "hora": request.form.get("hora_cita"),
                    "telefono": telefono
                }

                if not cita["hora"]:
                    conversacion.agregar_interaccion('bot', "⚠️ Selecciona una hora válida", None)
                else:
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
                                f"✅ Cita presencial confirmada para {cita['fecha']} a las {cita['hora']}. " 
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

# ===================== RUTA RESET =====================
@app.route("/reset", methods=["POST"])
def reset():
    try:
        session.clear()
        # Inicializar una nueva conversación con fechas_validas
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

# ===================== RUTAS DE MONITOREO DE APRENDIZAJE =====================
@app.route("/admin/aprendizaje")
@limiter.limit("10 per minute")
def monitoreo_aprendizaje():
    """Endpoint para monitorear el estado del aprendizaje del bot"""
    if "conversacion_data" not in session:
        return jsonify({"error": "No hay sesión activa"}), 400
    
    conversacion = SistemaConversacional.from_dict(session["conversacion_data"])
    
    return jsonify({
        "total_respuestas_aprendidas": sum(len(v) for v in conversacion.sistema_aprendizaje.respuestas_efectivas.values()),
        "sintomas_aprendidos": list(conversacion.sistema_aprendizaje.respuestas_efectivas.keys()),
        "patrones_detectados": len(conversacion.sistema_aprendizaje.patrones_conversacion),
        "engagement_actual": conversacion.engagement_actual
    })

@app.route("/admin/reiniciar-aprendizaje", methods=["POST"])
@limiter.limit("5 per minute")
def reiniciar_aprendizaje():
    """Reinicia el sistema de aprendizaje (solo para desarrollo)"""
    if os.environ.get('FLASK_ENV') == 'production':
        return jsonify({"error": "No disponible en producción"}), 403
    
    if "conversacion_data" in session:
        conversacion = SistemaConversacional.from_dict(session["conversacion_data"])
        conversacion.sistema_aprendizaje = SistemaAprendizaje()  # Reiniciar aprendizaje
        session["conversacion_data"] = conversacion.to_dict()
    
    return jsonify({"status": "Aprendizaje reiniciado"})

# ===================== RUTAS ADICIONALES =====================
@app.route("/verificar-horario", methods=["POST"])
def verificar_horario():
    try:
        data = request.get_json()
        if not data or 'fecha' not in data or 'hora' not in data:
            return jsonify({"error": "Datos incompletos"}), 400
            
        service = get_calendar_service()
        if not service:
            return jsonify({"error": "Servicio de calendario no disponible"}), 500
            
        eventos = service.events().list(
            calendarId='primary',
            timeMin=f"{data['fecha']}T{data['hora']}:00-05:00",
            timeMax=f"{data['fecha']}T{int(data['hora'].split(':')[0])+1}:00:00-05:00",
            singleEvents=True
        ).execute()
        return jsonify({"disponible": len(eventos.get('items', [])) == 0})
    except HttpError as error:
        app.logger.error(f"Error de Google API: {error}")
        return jsonify({"error": str(error)}), 500
    except Exception as e:
        app.logger.error(f"Error inesperado al verificar horario: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

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

# ===================== CONFIGURACIÓN PARA RENDER =====================
if __name__ == "__main__":
    # Verificar variables de entorno críticas en producción
    if os.environ.get('FLASK_ENV') == 'production':
        required_env_vars = ["FLASK_SECRET_KEY", "EMAIL_USER", "EMAIL_PASSWORD", "PSICOLOGO_EMAIL", "GOOGLE_CREDENTIALS", "GROQ_API_KEY"]
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing_vars:
            app.logger.error(f"ERROR: Variables de entorno faltantes en producción: {missing_vars}")
            exit(1)
    
    # Inicializar directorios necesarios
    for directory in ["logs", "conversaciones", "datos"]:
        if not os.path.exists(directory):
            os.makedirs(directory)
    
    # Usar el puerto que Render proporciona
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    app.logger.info(f"Iniciando aplicación Equilibra en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)