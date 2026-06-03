"""
Constantes globales de la aplicación Equilibra.
Única fuente de verdad para listas y valores compartidos entre módulos.
"""

import re as _re

# Patrones de detección de crisis (expresiones regulares)
CRISIS_PATTERNS = [
    r'suicidio', r'autolesión', r'autoflagelo', r'matarme',
    r'no\s+quiero\s+vivir', r'acabar\s+con\s+todo',
    r'no\s+vale\s+la\s+pena', r'sin\s+esperanza',
    r'quiero\s+morir', r'terminar\s+con\s+todo',
    r'me\s+quiero\s+morir', r'acabar\s+con\s+mi\s+vida',
    r'no\s+puedo\s+m[aá]s', r'estoy\s+harto(a)?', r'sin\s+sentido',
    r'despedirme', r'adios', r'no\s+aguanto', r'cansado(a)?\s+de\s+vivir',
    r'desesperado',
]

CRISIS_RESPONSE = (
    "Veo que estás pasando por un momento muy difícil. "
    "Es importante que hables con un profesional de inmediato.\n\n"
    "Líneas de ayuda inmediata:\n"
    "• Línea de crisis: 911\n"
    "• Tu psicólogo de confianza\n"
    "• Servicios de emergencia local\n\n"
    "No estás solo/a — busca ayuda profesional ahora."
)


def detectar_crisis(texto: str) -> bool:
    """Devuelve True si el texto contiene indicadores de crisis."""
    texto_lower = texto.lower()
    return any(_re.search(p, texto_lower) for p in CRISIS_PATTERNS)


SINTOMAS_DISPONIBLES = [
    "Ansiedad",
    "Tristeza",
    "Estrés",
    "Soledad",
    "Miedo",
    "Culpa",
    "Inseguridad",
    "Enojo",
    "Agotamiento emocional",
    "Falta de motivación",
    "Problemas de sueño",
    "Dolor corporal",
    "Preocupación excesiva",
    "Cambios de humor",
    "Apatía",
    "Sensación de vacío",
    "Pensamientos negativos",
    "Llanto frecuente",
    "Dificultad para concentrarse",
    "Desesperanza",
    "Tensión muscular",
    "Taquicardia",
    "Dificultad para respirar",
    "Problemas de alimentación",
    "Pensamientos intrusivos",
    "Problemas familiares",
    "Problemas de pareja",
]
