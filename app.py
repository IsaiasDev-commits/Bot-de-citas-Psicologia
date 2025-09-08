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

# CONFIGURACIÓN INICIAL 
load_dotenv()
env = Env()
env.read_env()

# Log inicial para debug
print("Python version:", sys.version)
print("Current directory:", os.getcwd())
print("Files in directory:", os.listdir('.'))

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

if not os.path.exists("conversaciones"):
    os.makedirs("conversaciones")

# FUNCIÓN PARA OLLAMA 
def generar_respuesta_llm(prompt, modelo="mistral"):
    """
    Envía un prompt al modelo de Ollama y devuelve la respuesta generada.
    """
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": modelo,
            "prompt": prompt,
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error de conexión con Ollama: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Error al generar respuesta con Ollama: {e}")
        return None

# FUNCIONES DE UTILIDAD 
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

def necesita_profesional(sintoma, duracion_dias, historial):
    if duracion_dias > 30:
        return True
    if historial and any(palabra in historial[-1]['mensaje'].lower() 
                         for palabra in ["suicidio", "autoflagelo", "no puedo más"]):
        return True
    return False

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

# Respuestas por síntoma (versión abreviada)
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
        "Conectar con otros lleva tiempo, y está bien tomarse ese proceso con calma.",
        "¿Te gustaría imaginar cómo sería un vínculo que te dé contención?",
        "A veces estar acompañado por alguien no significa dejar de sentir soledad. ¿Lo has sentido?",
        "¿Qué podrías hacer hoy que te haga sentir parte de algo, aunque sea pequeño?",
        "¿Hay alguna comunidad o espacio que quisieras explorar?",
        "Recuerda que mereces sentirte valorado y escuchado."
    ],
    "Miedo": [
        "El miedo es una emoción natural que nos protege, pero no debe paralizarnos.",
        "¿Puedes identificar qué te provoca miedo exactamente?",
        "Hablar de tus miedos puede ayudarte a entenderlos mejor.",
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
        "¿La culpa viene de una expectativa tuya o de los demás?",
        "Podemos aprender de lo que pasó sin cargarlo como un castigo eterno.",
        "Todos cometemos errores. La clave está en lo que haces con eso ahora.",
        "¿Hay algo que puedas hacer para reparar o aliviar esa carga?",
        "A veces la culpa no es real, sino impuesta. ¿De quién es esa voz interna?",
        "Eres humano. Equivocarte no te hace menos valioso.",
        "¿Qué le dirías a un amigo si estuviera en tu lugar?",
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
        "¿Has probado técnicas de relajación o estiramientos suaves?",
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
        "Reconocer la preocupación es el primer paso para manejarla.",
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
        "Tu bienestar es importante y hay caminos para mejorar."
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
        "No estás solo/a. Manyas personas pasan por esto más seguido de lo que imaginas.",
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
        "Sentir desesperanza es muy difícil, gracias por compartirlo.",
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
        "¿Quieres que te comparta recursos o estrategias para esto?",
        "Estoy aquí para escucharte y acompañarte siempre.",
        "La esperanza puede volver, paso a paso y con apoyo."
    ],
    "Tensión muscular": [
        "La tensión muscular puede ser síntoma de estrés o ansiedad.",
        "¿En qué partes de tu cuerpo sientes más tensión?",
        "Probar estiramientos suaves puede ayudarte a aliviar la tensión.",
        "¿Has intentado técnicas de relajación o respiración profunda?",
        "Hablar de tu estado puede ayudarte a identificar causas.",
        "¿Sientes que la tensión afecta tu movilidad o bienestar?",
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
# SISTEMA CONVERSACIONAL 
class SistemaConversacional:
    def __init__(self):
        self.historial = []
        self.respuestas_usadas = []  
        self.contexto_actual = None

    def obtener_respuesta_unica(self, sintoma):
        """Obtiene una respuesta no utilizada para el síntoma (fallback)"""
        respuestas_disponibles = [
            r for r in respuestas_por_sintoma.get(sintoma, []) 
            if r not in self.respuestas_usadas
        ]
        
        # Si ya usamos todas, reiniciamos el registro
        if not respuestas_disponibles:
            self.respuestas_usadas = []
            respuestas_disponibles = respuestas_por_sintoma.get(sintoma, [])
        
        # Seleccionar una respuesta al azar
        if respuestas_disponibles:
            respuesta = random.choice(respuestas_disponibles)
            self.respuestas_usadas.append(respuesta)
            return respuesta
        else:
            return "¿Puedes contarme más sobre cómo te sientes?"

    def analizar_contexto(self, user_input):
        """Detecta palabras clave para enriquecer el diálogo"""
        if not isinstance(user_input, str):
            return None

        user_input = user_input.lower()
        if any(palabra in user_input for palabra in ["tranquilo", "tranquilidad", "calma"]):
            return "Entiendo que buscas tranquilidad. ¿Qué suele ayudarte a encontrar calma?"
        elif any(palabra in user_input for palabra in ["vida", "normalmente", "cotidiano"]):
            return "Cuando dices que afecta tu vida normalmente, ¿en qué actividades concretas lo notas más?"
        elif any(palabra in user_input for palabra in ["familia", "pareja", "amigos", "compañeros"]):
            return "Las relaciones personales pueden ser complejas. ¿Cómo afecta esto a tus vínculos?"
        elif any(palabra in user_input for palabra in ["trabajo", "estudio", "productividad"]):
            return "¿Cómo está impactando esto en tu capacidad para concentrarte o cumplir con tus responsabilidades?"
        elif any(palabra in user_input for palabra in ["sueño", "dormir", "insomnio"]):
            return "El descanso es fundamental. ¿Cómo ha cambiado tu patrón de sueño recientemente?"
        return None

    def obtener_respuesta(self, sintoma, user_input):
        """Genera una respuesta contextual y empática"""
        # Detección de crisis
        palabras_crisis = ["suicidio", "autolesión", "autoflagelo", "matarme", "no quiero vivir", 
                          "acabar con todo", "no vale la pena", "sin esperanza"]
        if any(palabra in user_input.lower() for palabra in palabras_crisis):
            return "⚠️ Este tema es muy importante. Por favor, comunícate de inmediato con tu psicólogo o llama al número de emergencias 911."

        # Respuesta contextual
        respuesta_contextual = self.analizar_contexto(user_input)
        if respuesta_contextual:
            return respuesta_contextual

        # Intenta usar Ollama si está disponible
        try:
            prompt = f"""
            Eres un asistente empático que ayuda a las personas a reflexionar sobre sus emociones.
            El usuario menciona que siente: {sintoma}.
            Ha dicho: "{user_input}".
            Responde de manera comprensiva, breve y empática, sin reemplazar al psicólogo.
            """
            respuesta_ia = generar_respuesta_llm(prompt, modelo="mistral")
            if respuesta_ia and len(respuesta_ia) > 10 and "Error" not in respuesta_ia:
                return respuesta_ia
        except Exception as e:
            app.logger.error(f"Error al obtener respuesta de Ollama: {e}")

        # Fallback a respuestas predefinidas
        return self.obtener_respuesta_unica(sintoma)

    def agregar_interaccion(self, tipo, mensaje, sintoma=None):
        """Registra interacciones sin datos sensibles"""
        self.historial.append({
            'tipo': tipo,
            'mensaje': mensaje,
            'sintoma': sintoma,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        })

# GOOGLE CALENDAR 
def obtener_servicio_calendar():
    """Obtiene el servicio de Google Calendar"""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        return build('calendar', 'v3', credentials=credentials)
    except Exception as e:
        app.logger.error(f"Error obteniendo servicio de Calendar: {e}")
        return None

def crear_evento_calendar(nombre, email, telefono, fecha, hora, motivo):
    """Crea un evento en Google Calendar"""
    try:
        service = obtener_servicio_calendar()
        if not service:
            return False

        start_datetime = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        end_datetime = start_datetime + timedelta(hours=1)
        
        timezone = 'America/Montevideo'
        
        event = {
            'summary': f'Consulta Psicológica - {nombre}',
            'description': f'Paciente: {nombre}\nEmail: {email}\nTeléfono: {telefono}\nMotivo: {motivo}',
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': timezone,
            },
            'attendees': [
                {'email': email},
                {'email': 'psicologo@ejemplo.com'}  
            ],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 30},
                ],
            },
        }
        
        event = service.events().insert(calendarId='primary', body=event).execute()
        app.logger.info(f"Evento creado: {event.get('htmlLink')}")
        return True
        
    except HttpError as error:
        app.logger.error(f"Error al crear evento: {error}")
        return False
    except Exception as e:
        app.logger.error(f"Error inesperado: {e}")
        return False

# ENVÍO DE CORREOS 
def enviar_correo(destinatario, asunto, cuerpo):
    """Envía un correo electrónico"""
    try:
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = destinatario
        msg['Subject'] = asunto
        msg.attach(MIMEText(cuerpo, 'plain'))
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            
        app.logger.info(f"Correo enviado a {destinatario}")
        return True
        
    except Exception as e:
        app.logger.error(f"Error enviando correo: {e}")
        return False

# RUTAS FLASK 
@app.route('/')
def index():
    """Página principal"""
    # Limpiar sesión al inicio
    session.clear()
    
    # Preparar datos para el template
    fechas_validas = {
        'min_sintoma': (datetime.now() - timedelta(days=365*2)).strftime('%Y-%m-%d'),
        'max_sintoma': datetime.now().strftime('%Y-%m-%d'),
        'min_cita': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
        'max_cita': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
        'hoy': datetime.now().strftime('%Y-%m-%d')
    }
    
    return render_template('index.html', 
                         sintomas=sintomas_disponibles,
                         estado="inicio",
                         fechas_validas=fechas_validas)

@app.route('/procesar', methods=['POST'])
@csrf.exempt
def procesar():
    """Procesa el formulario principal"""
    try:
        # Inicializar sistema conversacional si no existe
        if 'sistema' not in session:
            session['sistema'] = SistemaConversacional()
            session['estado'] = 'inicio'

        sistema = session['sistema']
        estado_actual = session['estado']

        if estado_actual == 'inicio':
            # Procesar selección de síntoma
            sintoma = request.form.get('sintomas')
            if not sintoma:
                return redirect('/')
            
            session['sintoma_actual'] = sintoma
            session['estado'] = 'evaluacion'
            
            # Agregar mensaje inicial del bot
            sistema.agregar_interaccion('bot', f"He notado que mencionas {sintoma.lower()}. ¿Puedes contarme más sobre cómo te sientes?", sintoma)
            
            # Preparar fechas para el template
            fechas_validas = {
                'min_sintoma': (datetime.now() - timedelta(days=365*2)).strftime('%Y-%m-%d'),
                'max_sintoma': datetime.now().strftime('%Y-%m-%d'),
                'hoy': datetime.now().strftime('%Y-%m-%d')
            }
            
            return render_template('index.html',
                                sintomas=sintomas_disponibles,
                                estado='evaluacion',
                                conversacion=sistema,
                                sintoma_actual=sintoma,
                                fechas_validas=fechas_validas)

        elif estado_actual == 'evaluacion':
            # Procesar fecha de inicio del síntoma
            fecha_inicio = request.form.get('fecha_inicio_sintoma')
            duracion = calcular_duracion_dias(fecha_inicio)
            
            session['estado'] = 'profundizacion'
            
            # Agregar mensaje del bot sobre la duración
            sistema.agregar_interaccion('bot', f"Entiendo. Has estado experimentando esto por aproximadamente {duracion} días. ¿Quieres contarme más sobre cómo te afecta en tu día a día?", session.get('sintoma_actual'))
            
            # Preparar fechas para citas
            fechas_validas = {
                'min_cita': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                'max_cita': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            }
            
            return render_template('index.html',
                                estado='profundizacion',
                                conversacion=sistema,
                                sintoma_actual=session.get('sintoma_actual'),
                                fechas_validas=fechas_validas)

        elif estado_actual in ['profundizacion', 'derivacion']:
            # Procesar respuesta del usuario
            user_input = sanitizar_input(request.form.get('user_input', ''))
            
            if "cita" in user_input.lower() or "agendar" in user_input.lower() or request.form.get('solicitar_cita'):
                # Usuario quiere agendar cita
                session['estado'] = 'agendar_cita'
                sistema.agregar_interaccion('bot', "Entiendo que quieres agendar una cita. Por favor, completa los siguientes datos:")
                
                fechas_validas = {
                    'min_cita': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                    'max_cita': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                }
                
                return render_template('index.html',
                                    estado='agendar_cita',
                                    conversacion=sistema,
                                    fechas_validas=fechas_validas)
            else:
                # Continuar conversación normal
                sintoma = session.get('sintoma_actual', 'Ansiedad')
                sistema.agregar_interaccion('user', user_input, sintoma)
                respuesta = sistema.obtener_respuesta(sintoma, user_input)
                sistema.agregar_interaccion('bot', respuesta, sintoma)
                
                # Guardar sistema en sesión
                session['sistema'] = sistema
                
                fechas_validas = {
                    'min_cita': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
                    'max_cita': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                }
                
                return render_template('index.html',
                                    estado='profundizacion',
                                    conversacion=sistema,
                                    sintoma_actual=sintoma,
                                    fechas_validas=fechas_validas)

        elif estado_actual == 'agendar_cita':
            # Procesar agendamiento de cita
            # Aquí iría la lógica para procesar el formulario de cita
            session['estado'] = 'fin'
            sistema.agregar_interaccion('bot', "¡Gracias! Tu cita ha sido agendada. Te enviaremos un recordatorio por correo.")
            
            return render_template('index.html',
                                estado='fin',
                                conversacion=sistema)

    except Exception as e:
        app.logger.error(f"Error en procesar: {e}")
        return redirect('/')

@app.route('/reset', methods=['POST'])
def reset():
    """Reinicia la conversación"""
    session.clear()
    return jsonify({'status': 'success'})

@app.route('/verificar-horario', methods=['POST'])
def verificar_horario():
    """Verifica disponibilidad de horario"""
    try:
        data = request.get_json()
        fecha = data.get('fecha')
        hora = data.get('hora')
        
        # Simulación de verificación (en producción conectar con Google Calendar)
        disponible = random.choice([True, True, True, False])
        
        return jsonify({
            'disponible': disponible,
            'mensaje': 'Horario disponible' if disponible else 'Horario no disponible'
        })
        
    except Exception as e:
        app.logger.error(f"Error verificando horario: {e}")
        return jsonify({'error': 'Error interno'}), 500

@app.route('/solicitar-consulta', methods=['POST'])
@limiter.limit("5 per hour")
def solicitar_consulta():
    """Procesa la solicitud de consulta"""
    try:
        data = request.form
        
        # Validar y sanitizar datos
        nombre = sanitizar_input(data.get('nombre'))
        email = sanitizar_input(data.get('email'))
        telefono = sanitizar_input(data.get('telefono'))
        fecha = data.get('fecha')
        hora = data.get('hora')
        motivo = sanitizar_input(data.get('motivo'))
        
        # Validaciones básicas
        if not all([nombre, email, telefono, fecha, hora]):
            return jsonify({'error': 'Todos los campos son obligatorios'}), 400
            
        if not validar_telefono(telefono):
            return jsonify({'error': 'Teléfono inválido. Debe tener formato 09xxxxxxxx'}), 400
        
        # Crear evento en calendar (simulado por ahora)
        evento_creado = True  # crear_evento_calendar(nombre, email, telefono, fecha, hora, motivo)
        
        if evento_creado:
            # Enviar correo de confirmación (simulado por ahora)
            # enviar_correo(email, "Confirmación de consulta", 
            #              f"Hola {nombre}, tu consulta ha sido agendada para el {fecha} a las {hora}.")
            
            app.logger.info(f"Consulta agendada para {nombre} ({email})")
            return jsonify({
                'success': True, 
                'mensaje': 'Consulta agendada correctamente. Te hemos enviado un correo de confirmación.'
            })
        else:
            return jsonify({'error': 'Error al agendar la consulta. Intente nuevamente.'}), 500
            
    except Exception as e:
        app.logger.error(f"Error solicitando consulta: {e}")
        return jsonify({'error': 'Error interno del servidor'}), 500

# HANDLERS DE ERROR 
@app.errorhandler(404)
def pagina_no_encontrada(error):
    return jsonify({'error': 'Página no encontrada'}), 404

@app.errorhandler(413)
def demasiado_grande(error):
    return jsonify({'error': 'Archivo demasiado grande'}), 413

@app.errorhandler(429)
def demasiadas_solicitudes(error):
    return jsonify({'error': 'Demasiadas solicitudes. Por favor, espere un momento.'}), 429

@app.errorhandler(500)
def error_interno(error):
    return jsonify({'error': 'Error interno del servidor'}), 500

# EJECUCIÓN PRINCIPAL 
if __name__ == '__main__':
    # Configuración para Render
    port = int(os.environ.get('PORT', 5000))
    
    if os.environ.get('FLASK_ENV') == 'production':
        app.run(host='0.0.0.0', port=port)
    else:
        app.run(host='0.0.0.0', port=port, debug=True)