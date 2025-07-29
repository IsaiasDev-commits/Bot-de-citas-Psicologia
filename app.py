from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuración inicial
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not os.path.exists("conversaciones"):
    os.makedirs("conversaciones")

# ===================== LISTA DE SÍNTOMAS =====================
sintomas_disponibles = [
    "Ansiedad", "Tristeza", "Estrés", "Soledad", "Miedo", "Culpa", "Inseguridad",
    "Enojo", "Agotamiento emocional", "Falta de motivación", "Problemas de sueño",
    "Dolor corporal", "Preocupación excesiva", "Cambios de humor", "Apatía",
    "Sensación de vacío", "Pensamientos negativos", "Llanto frecuente",
    "Dificultad para concentrarse", "Desesperanza", "Tensión muscular",
    "Taquicardia", "Dificultad para respirar", "Problemas de alimentación",
    "Pensamientos intrusivos", "Problemas familiares", "Problemas de pareja"
]

# Respuestas por síntoma
respuestas_por_sintoma = {
    "Ansiedad": [
        "Respira profundamente y trata de enfocarte en el presente.",
        "¿Puedes identificar qué situaciones te generan más ansiedad?",
        "Hablar de tus miedos puede ayudarte a reducir su peso.",
        "¿Sientes que la ansiedad afecta tu cuerpo o solo tu mente?",
        "Intenta dar pequeños pasos para enfrentar lo que te preocupa.",
        "¿Has probado técnicas como la meditación o ejercicios de relajación?",
        "A veces, compartir lo que sientes puede aliviar la carga.",
        "¿Hay algo que te haga sentir más tranquilo momentáneamente?",
        "Recuerda que es normal tener altibajos en este proceso.",
        "¿Puedes contarme cuándo comenzó esta sensación de ansiedad?",
        "Mantener una rutina puede ayudar a manejar la ansiedad.",
        "¿Tienes apoyo cercano con quien puedas hablar sobre esto?",
        "Es importante reconocer los avances, por pequeños que sean.",
        "¿Hay pensamientos recurrentes que aumentan tu ansiedad?",
        "Si la ansiedad persiste, buscar ayuda profesional es recomendable."
    ],
    "Tristeza": [
        "Sentir tristeza es parte de la experiencia humana, está bien.",
        "¿Quieres contarme qué cosas te hacen sentir así?",
        "A veces, llorar puede ser una forma de liberar emociones.",
        "¿Has notado si hay momentos del día en que te sientes peor?",
        "La tristeza puede afectar tu energía, date permiso para descansar.",
        "¿Tienes alguien con quien puedas compartir lo que sientes?",
        "¿Hay actividades que antes disfrutabas y ahora no tanto?",
        "Hablar puede ser un primer paso para empezar a sanar.",
        "¿Qué cosas pequeñas te ayudan a sentir un poco mejor?",
        "Reconocer la tristeza es el primer paso para manejarla.",
        "¿Sientes que esta tristeza te impide hacer cosas importantes?",
        "Es válido buscar ayuda para atravesar momentos difíciles.",
        "¿Qué te gustaría cambiar para sentirte un poco mejor?",
        "¿Has tenido pensamientos negativos sobre ti mismo últimamente?",
        "Recuerda que no estás solo y que esto puede mejorar con apoyo."
    ],
     "Estrés": [
        "El estrés puede acumularse, es importante encontrar momentos para relajarte.",
        "¿Qué situaciones sientes que te generan más estrés?",
        "Probar ejercicios de respiración puede ayudarte a calmarte.",
        "¿Sientes tensión física cuando estás estresado?",
        "Hablar sobre lo que te preocupa puede aliviar la carga mental.",
        "¿Has intentado organizar tu tiempo para reducir el estrés?",
        "A veces es útil tomar pausas cortas durante el día.",
        "¿Qué actividades disfrutas que te ayuden a desconectar?",
        "¿Tienes alguien de confianza con quien puedas hablar?",
        "Reconocer el estrés es importante para poder manejarlo.",
        "¿Cómo afecta el estrés tu estado de ánimo o tus relaciones?",
        "Buscar apoyo puede facilitar encontrar soluciones.",
        "¿Has probado técnicas de relajación o mindfulness?",
        "Es bueno que estés buscando formas de cuidarte.",
        "Si el estrés es muy intenso, considera consultar con un especialista."
    ],
    "Soledad": [
        "Sentirse solo puede ser muy difícil, es bueno que lo expreses.",
        "¿Hay momentos o lugares donde te sientas más acompañado?",
        "Buscar actividades grupales puede ayudar a conectar con otros.",
        "¿Tienes algún amigo o familiar con quien puedas hablar?",
        "La soledad no siempre significa estar físicamente solo.",
        "¿Qué te gustaría que cambiara para sentirte mejor socialmente?",
        "Compartir tus sentimientos es un buen paso para aliviar la soledad.",
        "¿Hay cosas que disfrutas hacer aunque sea solo?",
        "Conectar con otros puede tomar tiempo, sé paciente contigo.",
        "¿Sientes miedo o inseguridad al acercarte a los demás?",
        "Es importante cuidar tu bienestar emocional en este proceso.",
        "¿Has intentado actividades nuevas para conocer gente?",
        "A veces, expresar lo que sientes ayuda a aliviar la carga.",
        "Recuerda que mereces compañía y apoyo.",
        "Si la soledad persiste, buscar ayuda puede ser beneficioso."
    ],
    "Miedo": [
        "El miedo es una emoción natural, hablar de él puede ayudar.",
        "¿Puedes identificar qué te causa miedo específicamente?",
        "¿Cómo reaccionas cuando sientes ese miedo?",
        "Enfrentar poco a poco los miedos puede disminuir su poder.",
        "¿Has intentado alguna técnica para relajarte en esos momentos?",
        "Compartir tus miedos puede ayudarte a entenderlos mejor.",
        "¿Sientes que el miedo limita algunas actividades de tu vida?",
        "Reconocer el miedo es el primer paso para manejarlo.",
        "¿Hay alguien en quien confíes para hablar sobre esto?",
        "Es válido buscar ayuda para enfrentar miedos persistentes.",
        "¿Qué cosas te hacen sentir seguro o protegido?",
        "A veces, los pensamientos negativos alimentan el miedo.",
        "¿Quieres contarme alguna experiencia relacionada con ese miedo?",
        "La valentía no es ausencia de miedo, sino enfrentarlo.",
        "Si el miedo interfiere mucho, un especialista puede apoyarte."
    ],
    "Culpa": [
        "Sentir culpa puede ser pesado, es bueno que lo compartas.",
        "¿Sobre qué situaciones sientes esa culpa?",
        "Es importante diferenciar entre culpa justa e injusta.",
        "Hablar sobre la culpa puede ayudarte a aliviarla.",
        "¿Sientes que la culpa afecta tu autoestima?",
        "¿Has intentado perdonarte a ti mismo por errores pasados?",
        "Reconocer la culpa es un paso para superarla.",
        "¿Qué cambios te gustaría hacer para sentirte mejor?",
        "La culpa excesiva puede ser dañina para tu bienestar.",
        "¿Tienes apoyo para hablar de estos sentimientos?",
        "Es válido buscar ayuda para manejar la culpa persistente.",
        "¿Cómo te afecta la culpa en tus relaciones personales?",
        "¿Puedes identificar pensamientos que aumentan la culpa?",
        "Perdonarte es parte del proceso de sanación.",
        "Si la culpa te abruma, considera hablar con un profesional."
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
        "¿Qué cosas te hacen sentir seguro o valorado?",
        "Aceptar tus imperfecciones es clave para superar inseguridades.",
        "¿Quieres contarme alguna experiencia donde te hayas sentido inseguro?",
        "La confianza se construye paso a paso, sé paciente contigo.",
        "Si la inseguridad limita tu vida, un profesional puede apoyarte."
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
        "¿Has probado técnicas para regular tus emociones?",
        "Dormir y alimentarte bien influye en tu estabilidad emocional.",
        "¿Hay algo que te ayude a sentirte más equilibrado?",
        "Es válido buscar ayuda profesional si los cambios son muy intensos.",
        "Recuerda que mereces sentirte bien y en paz contigo mismo."
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
        "Llorar puede ser una forma sana de liberar emociones.",
        "¿Quieres contarme qué te hace llorar con más frecuencia?",
        "Hablar de lo que sientes puede ayudarte a entender mejor tu llanto.",
        "¿Sientes alivio después de llorar o te cuesta mucho controlarlo?",
        "Reconocer tus emociones es un paso para manejar lo que sientes.",
        "¿Tienes alguien con quien puedas compartir tus sentimientos?",
        "Es válido llorar y expresar tus emociones sin juzgarte.",
        "¿Quieres contarme cómo te has sentido en general últimamente?",
        "Buscar apoyo puede ayudarte a entender por qué lloras tanto.",
        "¿Has notado si hay algo que desencadene ese llanto?",
        "Recuerda que mereces cuidado y comprensión en estos momentos.",
        "¿Has probado técnicas para manejar la emoción que sientes?",
        "Si el llanto es muy frecuente y afecta tu vida, busca ayuda.",
        "Estoy aquí para escucharte y acompañarte.",
        "Expresar tus sentimientos es parte de tu proceso de sanación."
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
        "Si la dificultad es constante, acude a un especialista pronto.",
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
        "Las relaciones pueden tener altibajos, es válido que busques apoyo.",
        "¿Te gustaría contarme qué está pasando con tu pareja?",
        "Expresar tus emociones puede ayudarte a entender mejor la situación.",
        "¿Sientes que tu relación te está afectando emocionalmente?",
        "Los conflictos de pareja son comunes, pero mereces sentirte escuchado/a.",
        "¿Qué te gustaría que mejorara en la relación?",
        "El respeto mutuo es clave en cualquier relación.",
        "¿Tienes a alguien con quien hablar cuando las cosas se complican con tu pareja?",
        "Está bien pedir ayuda si sientes que estás cargando con mucho emocionalmente.",
        "¿Sientes que la comunicación con tu pareja está funcionando?",
        "Estás haciendo bien al buscar una forma sana de manejar esto.",
        "No estás solo/a, muchos pasan por dificultades en sus relaciones.",
        "Hablar con un profesional puede ser útil para aclarar tus sentimientos.",
        "¿Quieres compartir cómo empezó esta situación con tu pareja?",
        "Tú mereces una relación que te aporte tranquilidad y bienestar."
    ]
}

# Diccionario de palabras clave para cada síntoma
keywords_por_sintoma = {
    "Problemas de pareja": ["pareja", "novio", "novia", "esposo", "esposa", "relación", "matrimonio"],
    "Problemas familiares": ["familia", "padres", "hermanos", "casa", "hogar", "papá", "mamá"],
    "Ansiedad": ["ansiedad", "nervios", "angustia", "pánico"],
    "Tristeza": ["tristeza", "deprimido", "desanimado", "desesperanzado"],
    "Estrés": ["estrés", "presión", "agobiado", "tensión"],
    "Soledad": ["solo", "soledad", "aislado", "incomprendido"],
    "Miedo": ["miedo", "temor", "aterrado", "pánico"],
    "Culpa": ["culpa", "arrepentido", "remordimiento"],
    "Inseguridad": ["inseguro", "duda", "incertidumbre"],
    "Enojo": ["enojo", "ira", "enfado", "rabia"],
    "Agotamiento emocional": ["agotado", "cansancio emocional", "quemado"],
    "Falta de motivación": ["desmotivado", "sin ganas", "apatía"],
    "Problemas de sueño": ["insomnio", "no duermo", "sueño interrumpido"],
    "Dolor corporal": ["dolor", "molestia", "tensión muscular"],
    "Preocupación excesiva": ["preocupación", "obsesión", "rumiación"],
    "Cambios de humor": ["altibajos", "cambios de ánimo", "volátil"],
    "Apatía": ["apatía", "indiferencia", "desinterés"],
    "Sensación de vacío": ["vacío", "hueco", "sin sentido"],
    "Pensamientos negativos": ["negatividad", "pesimismo", "derrotista"],
    "Llanto frecuente": ["llorar", "llanto", "lágrimas"],
    "Dificultad para concentrarse": ["concentración", "distracción", "enfoque"],
    "Desesperanza": ["desesperanza", "sin futuro", "pesimismo"],
    "Tensión muscular": ["tensión", "rigidez", "contractura"],
    "Taquicardia": ["taquicardia", "corazón acelerado", "palpitaciones"],
    "Dificultad para respirar": ["falta de aire", "disnea", "ahogo"],
    "Problemas de alimentación": ["comer", "alimentación", "dieta"],
    "Pensamientos intrusivos": ["intrusivos", "pensamientos no desead", "obsesivos"]
}

# ===================== FUNCIÓN PARA MANTENER CONTEXTO =====================
def obtener_respuesta_coherente(user_input, sintomas_seleccionados, conversacion):
    # Paso 1: Detectar el síntoma activo basado en palabras clave
    sintoma_activo = None
    for sintoma, keywords in keywords_por_sintoma.items():
        if any(keyword in user_input.lower() for keyword in keywords):
            sintoma_activo = sintoma
            break
    
    # Paso 2: Si no se detectó, usar el último síntoma mencionado
    if not sintoma_activo:
        for msg in reversed(conversacion):
            if msg["sender"] == "user":
                for sintoma in sintomas_seleccionados:
                    if sintoma.lower() in msg["message"].lower():
                        sintoma_activo = sintoma
                        break
    
    # Paso 3: Obtener respuesta coherente
    if sintoma_activo and sintoma_activo in respuestas_por_sintoma:
        respuestas = respuestas_por_sintoma[sintoma_activo]
        mensajes_bot = [msg["message"] for msg in conversacion if msg["sender"] == "bot"]
        # Evitar repetir la misma respuesta
        respuesta = next((r for r in respuestas if r not in mensajes_bot), respuestas[0])
        return respuesta
    
    return None  # Si no hay contexto claro

# ===================== CONFIGURACIÓN GOOGLE CALENDAR =====================
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_CALENDAR_CREDENTIALS")

def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('calendar', 'v3', credentials=creds)

def verificar_disponibilidad(fecha, hora):
    try:
        service = get_calendar_service()
        start_time = f"{fecha}T{hora}:00-05:00"
        end_time = f"{fecha}T{int(hora.split(':')[0]) + 1}:00:00-05:00"

        eventos = service.events().list(
            calendarId='primary',
            timeMin=start_time,
            timeMax=end_time,
            singleEvents=True
        ).execute()

        return len(eventos.get('items', [])) == 0

    except HttpError as error:
        print(f"Error al verificar disponibilidad: {error}")
        return False

def crear_evento_calendar(fecha, hora, descripcion="Cita psicológica"):
    try:
        service = get_calendar_service()
        event = {
            'summary': descripcion,
            'start': {'dateTime': f"{fecha}T{hora}:00-05:00", 'timeZone': 'America/Guayaquil'},
            'end': {'dateTime': f"{fecha}T{int(hora.split(':')[0]) + 1}:00:00-05:00", 'timeZone': 'America/Guayaquil'},
            'description': 'Cita agendada a través del sistema Equilibra'
        }

        event = service.events().insert(calendarId='primary', body=event).execute()
        return True
    except HttpError as error:
        print(f"Error al crear evento: {error}")
        return False

# ===================== FUNCIONES AUXILIARES =====================
def get_fechas_validas():
    hoy = datetime.now()
    return {
        'hoy': hoy.strftime('%Y-%m-%d'),
        'min_cita': hoy.strftime('%Y-%m-%d'),
        'max_cita': (hoy + timedelta(days=30)).strftime('%Y-%m-%d'),
        'min_sintoma': (hoy - timedelta(days=365*5)).strftime('%Y-%m-%d'),
        'max_sintoma': hoy.strftime('%Y-%m-%d')
    }

def enviar_correo(destinatario, asunto, cuerpo):
    remitente = os.getenv("EMAIL_USER")
    contraseña = os.getenv("EMAIL_PASSWORD")

    if not remitente or not contraseña:
        print("❌ Error: Credenciales de email no configuradas")
        return False

    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(cuerpo, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as servidor:
            servidor.login(remitente, contraseña)
            servidor.send_message(msg)
        print("✅ Correo enviado con éxito.")
        return True
    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")
        return False

@app.route("/", methods=["GET", "POST"])
def index():
    # Inicialización de la sesión
    if "estado" not in session:
        session.clear()
        session.update({
            "estado": "inicio",
            "sintomas_seleccionados": [],
            "conversacion": [],
            "duracion_sintomas": {},
            "fechas_validas": get_fechas_validas()
        })

    # Manejo de POST requests
    if request.method == "POST":
        if session["estado"] == "inicio":
            if seleccionados := request.form.getlist("sintomas"):
                session["sintomas_seleccionados"] = seleccionados
                session["estado"] = "registrar_duracion"
                session["sintoma_actual"] = seleccionados[0]
            return redirect(url_for("index"))

        elif session["estado"] == "registrar_duracion":
            if fecha := request.form.get("fecha_inicio_sintoma"):
                sintoma = session["sintoma_actual"]
                session["duracion_sintomas"][sintoma] = fecha
                session["estado"] = "chat"
                session["conversacion"].append({
                    "sender": "bot", 
                    "message": f"Registré que tienes {sintoma.lower()} desde {fecha}. ¿Cómo ha sido esta experiencia?"
                })
            return redirect(url_for("index"))

        elif session["estado"] == "chat":
            if user_input := request.form.get("user_input", "").strip():
                session["conversacion"].append({"sender": "user", "message": user_input})
                
                # --- MEJORA CLAVE AQUÍ ---
                respuesta_coherente = obtener_respuesta_coherente(
                    user_input, 
                    session["sintomas_seleccionados"], 
                    session["conversacion"]
                )
                
                if respuesta_coherente:
                    session["conversacion"].append({"sender": "bot", "message": respuesta_coherente})
                elif any(p in user_input.lower() for p in ["cita", "consultar", "doctor", "psicólogo"]):
                    session["estado"] = "agendar_cita"
                    session["conversacion"].append({
                        "sender": "bot", 
                        "message": "Vamos a agendar tu cita. Por favor completa:"
                    })
            return redirect(url_for("index"))

        elif session["estado"] == "agendar_cita":
            if fecha := request.form.get("fecha_cita"):
                cita = {
                    "fecha": fecha,
                    "hora": request.form.get("hora_cita"),
                    "telefono": request.form.get("telefono", "").strip()
                }

                if not cita["hora"]:
                    session["conversacion"].append({
                        "sender": "bot", 
                        "message": "Por favor selecciona una hora válida."
                    })
                else:
                    # Verificar disponibilidad
                    if not verificar_disponibilidad(cita["fecha"], cita["hora"]):
                        session["conversacion"].append({
                            "sender": "bot", 
                            "message": "🚫 El horario ya está ocupado. Por favor elige otro."
                        })
                    else:
                        # Crear evento en Google Calendar
                        if crear_evento_calendar(cita["fecha"], cita["hora"]):
                            # Enviar email al psicólogo
                            cuerpo_email = f"""
                            📋 Nueva cita agendada:

                            • Fecha: {cita['fecha']}
                            • Hora: {cita['hora']}
                            • Teléfono: {cita['telefono'] or 'No proporcionado'}

                            Síntomas reportados:
                            - {", ".join(session['sintomas_seleccionados'])}
                            """
                            
                            if enviar_correo(
                                os.getenv("PSICOLOGO_EMAIL"),
                                f"📅 Nueva cita: {cita['fecha']} {cita['hora']}",
                                cuerpo_email
                            ):
                                confirmacion = f"""
                                ✅ Solicitud recibida para el {cita['fecha']} a las {cita['hora']}.
                                El psicólogo te contactará al número proporcionado.
                                """
                            else:
                                confirmacion = "✅ Solicitud recibida. (Error al notificar al psicólogo, pero se guardó tu cita)"
                                
                            session["conversacion"].append({"sender": "bot", "message": confirmacion})
                            session["estado"] = "fin"
                        else:
                            session["conversacion"].append({
                                "sender": "bot", 
                                "message": "❌ Error al agendar. Por favor intenta nuevamente."
                            })
                return redirect(url_for("index"))

    # Renderizar template
    return render_template(
        "index.html",
        estado=session["estado"],
        sintomas=sintomas_disponibles,
        history=session["conversacion"],
        sintoma_actual=session.get("sintoma_actual"),
        **session["fechas_validas"]
    )

# ===================== RUTAS ADICIONALES =====================
@app.route("/reset", methods=["POST"])
def reset_session():
    session.clear()
    return jsonify({"status": "success"})

@app.route("/cancelar", methods=["POST"])
def cancelar_cita():
    if "estado" in session and session["estado"] == "agendar_cita":
        session["estado"] = "chat"
    return jsonify({"redirect": url_for("index")})

@app.route("/verificar-horario", methods=["POST"])
def verificar_horario():
    data = request.get_json()
    disponible = verificar_disponibilidad(data["fecha"], data["hora"])
    return jsonify({"disponible": disponible, "mensaje": "Disponible" if disponible else "Horario ocupado"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)