"""
Servicio de IA con Strategy Pattern y Decorator Pattern
Implementa separación de responsabilidades y permite múltiples proveedores de IA
"""

import os
import time
import threading
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import re
from groq import Groq
from functools import wraps
import logging
from constants import CRISIS_PATTERNS, CRISIS_RESPONSE

logger = logging.getLogger(__name__)

# ==================== DECORATOR PATTERN ====================

def cache_response(max_size: int = 100, ttl: int = 3600):
    """
    Decorador para cachear respuestas de IA usando LRU cache
    """
    cache = {}
    cache_lock = threading.Lock()
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar clave de caché basada en argumentos
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            with cache_lock:
                # Verificar si está en caché y no ha expirado
                if cache_key in cache:
                    timestamp, response = cache[cache_key]
                    if time.time() - timestamp < ttl:
                        logger.info(f"✅ Respuesta obtenida del caché para {func.__name__}")
                        return response
                    else:
                        # Eliminar entrada expirada
                        del cache[cache_key]
            
            # Ejecutar función original
            response = func(*args, **kwargs)
            
            if response and len(response) > 10:
                with cache_lock:
                    # Limitar tamaño del caché
                    if len(cache) >= max_size:
                        # Eliminar la entrada más antigua
                        oldest_key = min(cache.keys(), key=lambda k: cache[k][0])
                        del cache[oldest_key]
                    
                    # Guardar en caché
                    cache[cache_key] = (time.time(), response)
                    logger.info(f"💾 Respuesta guardada en caché. Tamaño: {len(cache)}")
            
            return response
        return wrapper
    return decorator

def log_execution(func):
    """
    Decorador para logging de ejecución de funciones de IA
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.info(f"🚀 Iniciando {func.__name__} con args: {args}, kwargs: {kwargs}")
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"✅ {func.__name__} completado en {execution_time:.2f}s")
            return result
        except Exception as e:
            logger.error(f"❌ Error en {func.__name__}: {e}")
            raise
    
    return wrapper

# ==================== STRATEGY PATTERN ====================

class AIServiceStrategy(ABC):
    """Interfaz Strategy para servicios de IA."""

    @abstractmethod
    def generate_response(self, text: str, symptom: str = None) -> str:
        """Genera una respuesta de IA para el texto dado."""
        pass

    @abstractmethod
    def select_model(self, text_length: int, complexity: str) -> str:
        """Selecciona el modelo apropiado basado en la situación."""
        pass

class GroqAIService(AIServiceStrategy):
    """
    Implementación concreta usando Groq API
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("GROQ_API_KEY no configurada")
        
        self.client = Groq(api_key=self.api_key)
        self.available_models = {
            'high_quality': 'openai/gpt-oss-120b',
            'balanced': 'llama-3.1-70b-versatile',
            'fast': 'openai/gpt-oss-20b'
        }
    
    def select_model(self, text_length: int, complexity: str) -> str:
        """
        Selecciona el modelo de Groq más apropiado según la situación
        """
        if complexity == 'crisis' or text_length > 200:
            return self.available_models['high_quality']
        elif complexity == 'complejo' or text_length > 100:
            return self.available_models['balanced']
        else:
            return self.available_models['fast']
    
    @cache_response(max_size=100, ttl=3600)
    @log_execution
    def generate_response(self, text: str, symptom: str = None) -> str:
        """
        Genera respuesta usando Groq API con caching y logging
        """
        try:
            # Determinar complejidad del tema
            complexity = self._determine_complexity(text, symptom)
            
            # Seleccionar modelo óptimo
            model = self.select_model(len(text), complexity)
            
            logger.info(f"🔥🔥🔥 LLAMANDO A GROQ API REALMENTE 🔥🔥🔥")
            logger.info(f"📊 Modelo Groq: {model} | Texto: {len(text)} chars | Complejidad: {complexity}")
            logger.info(f"🔑 API Key configurada: {'SÍ' if self.api_key else 'NO'} (longitud: {len(self.api_key) if self.api_key else 0})")
            
            # Prompt profesional para psicólogo clínico
            system_prompt = """Eres un psicólogo profesional con enfoque clínico.

Debes responder con claridad, estructura y profundidad.

Reglas obligatorias de formato:

No usar emojis.
No usar markdown.
No usar símbolos decorativos.
No usar negritas.
No usar listas con viñetas.
No dejar frases incompletas.
No cortar preguntas.
Separar cada idea con una línea en blanco.
Desarrollar completamente cada recomendación.

Estructura obligatoria de respuesta:

Primero: breve validación emocional.
Segundo: análisis de la situación.
Tercero: recomendaciones prácticas desarrolladas.
Cuarto: preguntas reflexivas completas al final.

Mantén un tono profesional, empático y clínico."""
            
            # Crear prompt del usuario con contexto
            user_prompt = f"""Contexto del usuario:
Síntoma actual: {symptom}

Mensaje del usuario:
"{text}"

Responde ahora de forma estructurada y profesional."""
            
            logger.info(f"📝 Enviando solicitud a Groq API con modelo {model}...")
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=800,
                temperature=0.4,
            )
            
            logger.info(f"🎯🎯🎯 RESPUESTA REAL RECIBIDA DE GROQ 🎯🎯🎯")
            logger.info(f"✅ Respuesta generada con {model} - Tokens: {response.usage.total_tokens if response.usage else 'N/A'}")
            
            raw_response = response.choices[0].message.content
            
            # Limpiar respuesta (eliminar cualquier markdown residual)
            cleaned_response = self._clean_response(raw_response)
            
            logger.info(f"📝 Longitud respuesta: {len(raw_response)} -> {len(cleaned_response)} caracteres")
            logger.info(f"📋 Primeros 100 chars: {cleaned_response[:100]}...")
            
            return cleaned_response
            
        except Exception as e:
            logger.error(f"❌❌❌ ERROR en Groq API: {e}")
            logger.error(f"📌 Stack trace completo:", exc_info=True)
            return self._get_fallback_response(text)
    
    def _determine_complexity(self, text: str, symptom: str = None) -> str:
        """Determina la complejidad del tema basado en el texto y síntoma."""
        text_lower = text.lower()
        for pattern in CRISIS_PATTERNS:
            if re.search(pattern, text_lower):
                return 'crisis'

        complex_symptoms = ["Ansiedad", "Depresión", "Estrés", "Problemas familiares", "Problemas de pareja"]
        if len(text) > 150 or (symptom and symptom in complex_symptoms):
            return 'complejo'

        return 'normal'
    
    def _clean_response(self, response: str) -> str:
        """
        Limpia la respuesta eliminando markdown, emojis y formateando correctamente
        """
        if not response:
            return response
        
        # Eliminar markdown básico
        cleaned = response
        
        # Eliminar **negritas**
        cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)
        
        # Eliminar *cursivas*
        cleaned = re.sub(r'\*(.*?)\*', r'\1', cleaned)
        
        # Eliminar encabezados markdown (#, ##, ###)
        cleaned = re.sub(r'^#+\s*', '', cleaned, flags=re.MULTILINE)
        
        # Eliminar listas con viñetas o números
        cleaned = re.sub(r'^[\s]*[•\-*]\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'^[\s]*\d+[\.\)]\s*', '', cleaned, flags=re.MULTILINE)
        
        # Eliminar emojis comunes
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
            u"\U00002702-\U000027B0"  # dingbats
            u"\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        cleaned = emoji_pattern.sub('', cleaned)
        
        # Asegurar separación adecuada entre párrafos
        # Reemplazar múltiples saltos de línea por dos
        cleaned = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned)
        
        # Eliminar espacios en blanco al inicio y final
        cleaned = cleaned.strip()
        
        return cleaned
    
    def _get_fallback_response(self, text: str) -> str:
        if self._determine_complexity(text) == 'crisis':
            return CRISIS_RESPONSE
        return "Entiendo que estás pasando por un momento difícil. ¿Te gustaría contarme más sobre cómo te sientes?"

class FallbackAIService(AIServiceStrategy):
    """
    Servicio de IA de fallback que usa respuestas predefinidas
    """
    
    def __init__(self):
        self.predefined_responses = {
            "Ansiedad": [
                "La ansiedad puede ser abrumadora. ¿Qué situaciones la desencadenan?",
                "Cuando sientes ansiedad, ¿qué técnicas has probado para calmarte?",
                "¿Notas que la ansiedad afecta tu cuerpo (ej. taquicardia, sudoración)?",
            ],
            "Tristeza": [
                "Sentir tristeza no significa debilidad. Es una señal de que algo importa.",
                "¿Qué eventos recientes han influido en tu estado de ánimo?",
                "Permítete sentir. Reprimir emociones no las hace desaparecer.",
            ],
            "general": [
                "Entiendo que estés pasando por un momento difícil. ¿Qué has intentado para manejar esta situación?",
                "Es completamente normal sentirse así. ¿Te gustaría hablar más sobre qué desencadenó estos sentimientos?",
                "Agradezco que compartas esto conmigo. ¿Cómo ha afectado esto tu día a día?",
            ]
        }
    
    def select_model(self, text_length: int, complexity: str) -> str:
        return "fallback"

    def generate_response(self, text: str, symptom: str = None) -> str:
        import random
        
        if symptom and symptom in self.predefined_responses:
            responses = self.predefined_responses[symptom]
        else:
            responses = self.predefined_responses["general"]
        
        return random.choice(responses)

# ==================== FACTORY PATTERN ====================

class AIServiceFactory:
    """Factory para crear instancias de servicios de IA con soporte de singleton."""

    _instance: Optional[AIServiceStrategy] = None
    _lock = threading.Lock()

    @staticmethod
    def create_service(service_type: str = "groq", **kwargs) -> AIServiceStrategy:
        services = {
            "groq": GroqAIService,
            "fallback": FallbackAIService,
        }
        if service_type not in services:
            logger.warning(f"Servicio '{service_type}' no encontrado, usando fallback")
            service_type = "fallback"
        try:
            return services[service_type](**kwargs)
        except Exception as e:
            logger.error(f"Error creando servicio {service_type}: {e}")
            return FallbackAIService()

    @classmethod
    def get_instance(cls) -> AIServiceStrategy:
        """
        Retorna la instancia singleton del servicio de IA.
        Se inicializa una sola vez al primer acceso y se reutiliza en todos los requests.
        """
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                groq_key = os.getenv('GROQ_API_KEY')
                if groq_key:
                    try:
                        cls._instance = GroqAIService(api_key=groq_key)
                        logger.info("Singleton AIService inicializado con Groq")
                    except Exception as e:
                        logger.error(f"Error inicializando Groq, usando fallback: {e}")
                        cls._instance = FallbackAIService()
                else:
                    logger.warning("GROQ_API_KEY no configurada — usando FallbackAIService")
                    cls._instance = FallbackAIService()
        return cls._instance

# ==================== USO EJEMPLO ====================

if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    # Crear servicio usando factory
    ai_service = AIServiceFactory.create_service("groq")
    
    # Generar respuesta (con caching automático)
    response = ai_service.generate_response(
        text="Me siento muy ansioso últimamente, no puedo dormir",
        symptom="Ansiedad"
    )
    
    print(f"Respuesta generada:\n{response}")