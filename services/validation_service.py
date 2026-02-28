"""
Servicio de validación usando Template Method Pattern
Separa la lógica de validación de horarios y citas
"""

from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)

# ==================== TEMPLATE METHOD PATTERN ====================

class ScheduleValidator(ABC):
    """
    Clase base abstracta para validadores de horarios usando Template Method Pattern
    """
    
    def validate(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """
        Template method que define el esqueleto del algoritmo de validación
        """
        try:
            # 1. Validar formato básico
            is_valid, message = self._validate_format(date_str, time_str)
            if not is_valid:
                return False, message
            
            # 2. Validar que no sea en el pasado
            is_valid, message = self._validate_not_past(date_str, time_str)
            if not is_valid:
                return False, message
            
            # 3. Validar día de la semana
            is_valid, message = self._validate_weekday(date_str, time_str)
            if not is_valid:
                return False, message
            
            # 4. Validar horario laboral (implementación específica)
            is_valid, message = self._validate_business_hours(date_str, time_str)
            if not is_valid:
                return False, message
            
            # 5. Validar tiempo mínimo para agendar
            is_valid, message = self._validate_minimum_advance(date_str, time_str)
            if not is_valid:
                return False, message
            
            # 6. Validaciones adicionales específicas
            is_valid, message = self._validate_additional_rules(date_str, time_str)
            if not is_valid:
                return False, message
            
            return True, "Horario válido"
            
        except ValueError as e:
            return False, f"Formato de fecha/hora inválido: {str(e)}"
        except Exception as e:
            logger.error(f"Error en validación: {e}")
            return False, f"Error en validación: {str(e)}"
    
    def _validate_format(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """Validar formato básico de fecha y hora"""
        try:
            datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            return True, ""
        except ValueError:
            return False, "Formato de fecha u hora inválido. Use YYYY-MM-DD y HH:MM"
    
    def _validate_not_past(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """Validar que la cita no sea en el pasado"""
        appointment_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        now = datetime.now()
        
        if appointment_time <= now:
            return False, "No se pueden agendar citas en horarios pasados"
        
        return True, ""
    
    def _validate_weekday(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """Validar día de la semana"""
        appointment_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        weekday = appointment_time.weekday()
        
        if weekday == 6:  # Domingo
            return False, "No hay atención los domingos"
        
        return True, ""
    
    @abstractmethod
    def _validate_business_hours(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """
        Método abstracto que debe ser implementado por subclases
        para validar horarios laborales específicos
        """
        pass
    
    def _validate_minimum_advance(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """Validar tiempo mínimo para agendar (30 minutos)"""
        appointment_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        now = datetime.now()
        minimum_advance = timedelta(minutes=30)
        
        if appointment_time - now < minimum_advance:
            return False, "Debe agendar con al menos 30 minutos de anticipación"
        
        return True, ""
    
    def _validate_additional_rules(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """
        Hook method para validaciones adicionales
        Las subclases pueden sobrescribir este método si necesitan reglas adicionales
        """
        appointment_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        now = datetime.now()
        
        # Restricción adicional: No permitir agendar para el mismo día después de las 18:00
        if (appointment_time.date() == now.date() and 
            now.hour >= 18 and appointment_time.hour >= 18):
            return False, "No se pueden agendar citas para hoy después de las 18:00"
        
        return True, ""

class WeekdayValidator(ScheduleValidator):
    """
    Validador para días laborales (Lunes a Viernes)
    """
    
    def _validate_business_hours(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """Validar horario laboral de Lunes a Viernes: 14:00 - 19:00"""
        hour = int(time_str.split(':')[0])
        
        if not (14 <= hour <= 19):
            return False, "Horario no disponible. Lunes a Viernes: 14:00 - 19:00"
        
        return True, ""

class SaturdayValidator(ScheduleValidator):
    """
    Validador para sábados
    """
    
    def _validate_business_hours(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """Validar horario laboral de Sábados: 08:00 - 14:00"""
        hour = int(time_str.split(':')[0])
        
        if not (8 <= hour <= 14):
            return False, "Horario no disponible. Sábados: 08:00 - 14:00"
        
        return True, ""

# ==================== FACTORY PATTERN ====================

class ValidatorFactory:
    """
    Factory para crear validadores basados en la fecha
    """
    
    @staticmethod
    def create_validator(date_str: str) -> ScheduleValidator:
        """
        Crea un validador apropiado basado en el día de la semana
        """
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            weekday = date.weekday()
            
            if weekday in [0, 1, 2, 3, 4]:  # Lunes a Viernes
                return WeekdayValidator()
            elif weekday == 5:  # Sábado
                return SaturdayValidator()
            else:  # Domingo
                # Aunque no debería llegar aquí porque ya se valida en _validate_weekday
                return WeekdayValidator()  # Fallback
                
        except ValueError:
            # Si hay error en el formato, retornar validador por defecto
            return WeekdayValidator()

# ==================== SERVICIO DE VALIDACIÓN UNIFICADO ====================

class ValidationService:
    """
    Servicio unificado de validación que usa los validadores específicos
    """
    
    def __init__(self):
        self.validator_factory = ValidatorFactory()
    
    def validate_appointment_time(self, date_str: str, time_str: str) -> Tuple[bool, str]:
        """
        Valida un horario de cita usando el validador apropiado
        """
        validator = self.validator_factory.create_validator(date_str)
        return validator.validate(date_str, time_str)
    
    def get_available_time_slots(self, date_str: str) -> list:
        """
        Obtiene horarios disponibles para una fecha específica
        """
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            weekday = date.weekday()
            now = datetime.now()
            is_today = date.date() == now.date()
            
            # Definir horarios base según día
            if weekday in [0, 1, 2, 3, 4]:  # Lunes a Viernes
                base_slots = ["14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]
            elif weekday == 5:  # Sábado
                base_slots = ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]
            else:  # Domingo
                return []
            
            available_slots = []
            
            for time_slot in base_slots:
                # Validar cada horario
                is_valid, message = self.validate_appointment_time(date_str, time_slot)
                
                if is_valid:
                    # Verificación adicional: para hoy, filtrar horarios que ya pasaron
                    if is_today:
                        current_hour = now.hour
                        current_minute = now.minute
                        slot_hour = int(time_slot.split(':')[0])
                        
                        # Si la hora de la cita ya pasó, no mostrar
                        if slot_hour < current_hour or (slot_hour == current_hour and current_minute >= 0):
                            continue
                    
                    available_slots.append({
                        'hora': time_slot,
                        'disponible': True,
                        'mensaje': 'Disponible'
                    })
            
            return available_slots
            
        except ValueError:
            return []
    
    def validate_phone(self, phone: str) -> Tuple[bool, str]:
        """
        Valida un número de teléfono
        """
        import re
        
        if not phone:
            return False, "Teléfono requerido"
        
        # Limpiar caracteres no numéricos
        clean_phone = re.sub(r'[^\d]', '', phone)
        
        if len(clean_phone) != 10:
            return False, "El teléfono debe tener 10 dígitos"
        
        if not clean_phone.startswith('09'):
            return False, "El teléfono debe comenzar con 09"
        
        return True, ""

# ==================== USO EJEMPLO ====================

if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    # Crear servicio de validación
    validation_service = ValidationService()
    
    # Probar validación de horario
    test_cases = [
        ("2025-01-01", "14:00"),  # Lunes laboral
        ("2025-01-01", "20:00"),  # Fuera de horario
        ("2025-01-04", "10:00"),  # Sábado válido
        ("2025-01-05", "10:00"),  # Domingo inválido
    ]
    
    for date, time in test_cases:
        is_valid, message = validation_service.validate_appointment_time(date, time)
        status = "✅ VÁLIDO" if is_valid else "❌ INVÁLIDO"
        print(f"{date} {time}: {status} - {message}")
    
    # Probar obtención de horarios disponibles
    print("\n📅 Horarios disponibles para 2025-01-01 (Lunes):")
    available_slots = validation_service.get_available_time_slots("2025-01-01")
    for slot in available_slots:
        print(f"  • {slot['hora']} - {slot['mensaje']}")
    
    # Probar validación de teléfono
    phone_tests = ["0991234567", "0912345678", "1234567890", "099-123-4567"]
    print("\n📱 Validación de teléfonos:")
    for phone in phone_tests:
        is_valid, message = validation_service.validate_phone(phone)
        status = "✅ VÁLIDO" if is_valid else "❌ INVÁLIDO"
        print(f"  {phone}: {status} - {message}")