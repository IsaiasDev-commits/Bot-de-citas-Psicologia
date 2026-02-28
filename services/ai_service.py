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
import html
from groq import Groq
from functools import wraps
import logging

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
    """
    Interfaz Strategy para servicios de IA
    """
    
    @abstractmethod
    def generate_response(self, text: str, symptom: str = None) -> str:
        """
        Genera una respuesta de IA para el texto dado
        """
        pass
    
    @abstractmethod
    def select_model(self, text_length: int, complexity: str) -> str:
        """
        Selecciona el modelo apropiado basado en la situación
        """
        pass
    
    @abstractmethod
    def format_response(self, raw_response: str) -> str:
        """
        Formatea la respuesta de IA para mejor presentación
        """
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
    
    def format_response(self, raw_response: str) -> str:
        """
        Formatea la respuesta de la IA para separar ideas y consejos
        """
        if not raw_response:
            return raw_response
        
        # Patrones para detectar diferentes tipos de contenido
        advice_patterns = [
            r'(\d+[\.\)]?\s*)',  # 1. 2) etc.
            r'[•\-]\s*',         # • - 
            r'Consejo\s*\d*:',   # Consejo 1:
            r'Recomendación\s*\d*:',  # Recomendación 2:
            r'Sugerencia\s*\d*:',     # Sugerencia 3:
            r'💡',                # Emoji de bombilla
            r'⭐',                # Emoji de estrella
            r'📝',               # Emoji de notas
        ]
        
        # Dividir el texto en párrafos
        paragraphs = raw_response.split('\n\n')
        formatted_text = []
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # Verificar si el párrafo contiene consejos numerados o con viñetas
            is_advice_list = any(re.search(pattern, paragraph) for pattern in advice_patterns)
            
            if is_advice_list:
                # Mejorar el formato de listas
                lines = paragraph.split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        if re.match(r'(\d+[\.\)])', line):
                            line = f"⭐ {line}"
                        elif re.match(r'[•\-]', line):
                            line = f"💡 {line[1:].strip() if line.startswith('•') or line.startswith('-') else line}"
                        elif 'consejo' in line.lower() or 'recomendación' in line.lower() or 'sugerencia' in line.lower():
                            line = f"📝 {line}"
                        
                        formatted_text.append(line)
                formatted_text.append("")  # Línea en blanco entre secciones
            else:
                # Párrafos normales
                formatted_text.append(paragraph)
                formatted_text.append("")  # Línea en blanco entre párrafos
        
        # Unir todo y limpiar líneas en blanco excesivas
        result = '\n'.join(formatted_text).strip()
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
        
        return result
    
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
            
            logger.info(f"Usando modelo Groq: {model} para texto de {len(text)} caracteres, complejidad: {complexity}")
            
            # Prompt especializado para apoyo psicológico
            system_prompt = self._get_system_prompt()
            
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                max_tokens=600,
                temperature=0.7,
            )
            
            raw_response = response.choices[0].message.content
            
            # Aplicar formato estructurado
            formatted_response = self.format_response(raw_response)
            
            # Log del uso del modelo
            logger.info(f"✅ Respuesta generada con {model} - Tokens: {response.usage.total_tokens if response.usage else 'N/A'}")
            logger.info(f"📝 Longitud respuesta: {len(raw_response)} -> {len(formatted_response)} caracteres")
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error al generar respuesta con Groq: {e}")
            return self._get_fallback_response(text)
    
    def _determine_complexity(self, text: str, symptom: str = None) -> str:
        """
        Determina la complejidad del tema basado en el texto y síntoma
        """
        crisis_keywords = [
            r'suicidio', r'autolesión', r'autoflagelo', r'matarme', 
            r'no\s+quiero\s+vivir', r'acabar\s+con\s+todo', 
            r'no\s+vale\s+la\s+pena', r'sin\s+esperanza', 
            r'quiero\s+morir', r'terminar\s+con\s+todo',
            r'me\s+quiero\s+morir', r'acabar\s+con\s+mi\s+vida',
            r'no\s+puedo\s+más', r'estoy\s+harto(a)?', r'sin\s+sentido',
            r'despedirme', r'adios', r'no\s+aguanto', r'cansado(a)?\s+de\s+vivir'
        ]
        
        text_lower = text.lower()
        for pattern in crisis_keywords:
            if re.search(pattern, text_lower):
                return 'crisis'
        
        complex_symptoms = ["Ansiedad", "Depresión", "Estrés", "Problemas familiares", "Problemas de pareja"]
        if len(text) > 150 or (symptoma and symptom in complex_symptoms):
            return 'complejo'
        
        return 'normal'
    
    def _get_system_prompt(self) -> str:
        """
        Retorna el prompt del sistema para apoyo psicológico
        """
        return """Eres un asistente psicológico profesional, empático y compasivo. Tu objetivo es:

1. **Validar emociones**: Reconocer y validar los sentimientos del usuario
2. **Ofrecer apoyo**: Proporcionar contención emocional inmediata  
3. **Guiar sin diagnosticar**: Orientar sin hacer diagnósticos médicos
4. **Fomentar autocuidado**: Sugerir técnicas de regulación emocional
5. **Derivar cuando sea necesario**: Recomendar buscar ayuda profesional en casos graves

**FORMATO DE RESPUESTA ESTRUCTURADO:**

- **Empieza con validación emocional**: "Entiendo que..." "Es normal sentir..."
- **Separa claramente las ideas** usando párrafos
- **Para consejos prácticos**, usa formato de lista con:
  • Viñetas (•) o números (1. 2. 3.)
  • Emojis relevantes (💡, ⭐, 🌱, 🧘‍♀️, 📝)
  • Títulos claros como "Consejos prácticos:" o "Estrategias que pueden ayudar:"
- **Incluye preguntas reflexivas** al final para continuar la conversación
- **Mantén un tono cálido, profesional y esperanzador**
- **Evita lenguaje técnico excesivo**
- **En crisis graves**, recomienda contactar líneas de ayuda profesional inmediatamente

Ejemplo de formato ideal:

Entiendo que estés pasando por un momento de [emoción]. Es completamente normal sentirse así cuando...

💡 Algunas estrategias que pueden ayudarte:

Practica la respiración profunda por 5 minutos

Escribe tus pensamientos en un diario

Da un corto paseo al aire libre

¿Has probado alguna de estas técnicas? ¿Cómo te sientes al respecto?
"""
    
    def _get_fallback_response(self, text: str) -> str:
        """
        Retorna una respuesta de fallback en caso de error
        """
        if self._determine_complexity(text) == 'crisis':
            return "⚠️ **Crisis detectada**\n\nVeo que estás pasando por un momento muy difícil. Es importante que hables con un profesional de inmediato.\n\n📞 **Líneas de ayuda inmediata:**\n• Línea de crisis: 911\n• Tu psicólogo de confianza\n• Servicios de emergencia local\n\nNo estás solo/a, busca ayuda profesional ahora."
        
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
    
    def format_response(self, raw_response: str) -> str:
        return raw_response
    
    def generate_response(self, text: str, symptom: str = None) -> str:
        import random
        
        if symptom and symptom in self.predefined_responses:
            responses = self.predefined_responses[symptom]
        else:
            responses = self.predefined_responses["general"]
        
        return random.choice(responses)

# ==================== FACTORY PATTERN ====================

class AIServiceFactory:
    """
    Factory para crear instancias de servicios de IA
    """
    
    @staticmethod
    def create_service(service_type: str = "groq", **kwargs) -> AIServiceStrategy:
        """
        Crea una instancia del servicio de IA especificado
        """
        services = {
            "groq": GroqAIService,
            "fallback": FallbackAIService,
        }
        
        if service_type not in services:
            logger.warning(f"Servicio de IA '{service_type}' no encontrado, usando fallback")
            service_type = "fallback"
        
        service_class = services[service_type]
        
        try:
            return service_class(**kwargs)
        except Exception as e:
            logger.error(f"Error creando servicio {service_type}: {e}")
            return FallbackAIService()

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