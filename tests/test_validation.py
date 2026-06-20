"""Tests para ValidationService — teléfono, fechas y horarios de citas."""
import pytest
from datetime import date, timedelta
from services.validation_service import ValidationService

# Fechas fijas en el futuro lejano para que los tests no caduquen pronto.
# 2027-06-07 es lunes, 2027-06-12 es sábado.
_LUNES = "2027-06-07"
_SABADO = "2027-06-12"


@pytest.fixture(scope="module")
def svc():
    return ValidationService()


class TestValidatePhone:
    def test_telefono_valido(self, svc):
        ok, msg = svc.validate_phone("0991234567")
        assert ok is True

    def test_telefono_muy_corto(self, svc):
        ok, _ = svc.validate_phone("099123")
        assert ok is False

    def test_telefono_muy_largo(self, svc):
        ok, _ = svc.validate_phone("09912345678")
        assert ok is False

    def test_telefono_sin_prefijo_09(self, svc):
        ok, _ = svc.validate_phone("1234567890")
        assert ok is False

    def test_telefono_con_letras(self, svc):
        ok, _ = svc.validate_phone("099abcdefg")
        assert ok is False

    def test_telefono_vacio(self, svc):
        ok, _ = svc.validate_phone("")
        assert ok is False


class TestBusinessHoursWeekday:
    """Weekdays: valid 14:00-19:00, invalid outside that range."""

    def test_hora_valida_lunes(self, svc):
        ok, _ = svc.validate_appointment_time(_LUNES, "16:00")
        assert ok is True

    def test_hora_muy_temprana_rechazada(self, svc):
        ok, msg = svc.validate_appointment_time(_LUNES, "13:00")
        assert ok is False
        assert "14:00" in msg or "horario" in msg.lower()

    def test_hora_limite_inferior_valida(self, svc):
        ok, _ = svc.validate_appointment_time(_LUNES, "14:00")
        assert ok is True

    def test_hora_limite_superior_valida(self, svc):
        ok, _ = svc.validate_appointment_time(_LUNES, "19:00")
        assert ok is True

    def test_hora_fuera_de_rango_rechazada(self, svc):
        ok, _ = svc.validate_appointment_time(_LUNES, "20:00")
        assert ok is False


class TestBusinessHoursSaturday:
    """Saturdays: valid 08:00-14:00, invalid outside that range."""

    def test_hora_valida_sabado(self, svc):
        ok, _ = svc.validate_appointment_time(_SABADO, "10:00")
        assert ok is True

    def test_hora_limite_inferior_sabado(self, svc):
        ok, _ = svc.validate_appointment_time(_SABADO, "08:00")
        assert ok is True

    def test_hora_limite_superior_sabado(self, svc):
        ok, _ = svc.validate_appointment_time(_SABADO, "14:00")
        assert ok is True

    def test_hora_fuera_de_rango_sabado_rechazada(self, svc):
        ok, msg = svc.validate_appointment_time(_SABADO, "15:00")
        assert ok is False
        assert "08:00" in msg or "sábado" in msg.lower() or "sabado" in msg.lower()

    def test_slots_sabado_distintos_de_semana(self, svc):
        slots_lunes = svc.get_available_time_slots(_LUNES)
        slots_sabado = svc.get_available_time_slots(_SABADO)
        # Saturday starts at 08:00, weekdays start at 14:00
        horas_sabado = [s["hora"] for s in slots_sabado]
        horas_lunes = [s["hora"] for s in slots_lunes]
        assert "08:00" in horas_sabado
        assert "08:00" not in horas_lunes


class TestGetAvailableTimeSlots:
    def _future_weekday(self, days_ahead=3):
        """Retorna una fecha futura que caiga en día hábil (lunes-sábado)."""
        d = date.today() + timedelta(days=days_ahead)
        # Avanzar si es domingo
        while d.weekday() == 6:
            d += timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    def test_retorna_lista(self, svc):
        fecha = self._future_weekday()
        resultado = svc.get_available_time_slots(fecha)
        assert isinstance(resultado, (list, dict))

    def test_domingo_sin_horarios(self, svc):
        d = date.today()
        while d.weekday() != 6:
            d += timedelta(days=1)
        resultado = svc.get_available_time_slots(d.strftime("%Y-%m-%d"))
        if isinstance(resultado, list):
            assert resultado == []
        else:
            assert resultado.get("disponibles", []) == []

    def test_fecha_pasada_sin_horarios(self, svc):
        ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        resultado = svc.get_available_time_slots(ayer)
        if isinstance(resultado, list):
            assert resultado == []
        else:
            assert resultado.get("disponibles", []) == []


class TestValidateAppointmentTime:
    def _future_weekday(self, days_ahead=3):
        d = date.today() + timedelta(days=days_ahead)
        while d.weekday() == 6:
            d += timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    def test_domingo_rechazado(self, svc):
        d = date.today()
        while d.weekday() != 6:
            d += timedelta(days=1)
        ok, _ = svc.validate_appointment_time(d.strftime("%Y-%m-%d"), "10:00")
        assert ok is False

    def test_fecha_pasada_rechazada(self, svc):
        ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        ok, _ = svc.validate_appointment_time(ayer, "10:00")
        assert ok is False

    def test_formato_invalido_rechazado(self, svc):
        ok, _ = svc.validate_appointment_time("no-es-fecha", "10:00")
        assert ok is False

    def test_hora_invalida_rechazada(self, svc):
        ok, _ = svc.validate_appointment_time(_LUNES, "99:99")
        assert ok is False

    def test_mensaje_de_error_no_vacio(self, svc):
        ok, msg = svc.validate_appointment_time("2020-01-01", "10:00")
        assert ok is False
        assert len(msg) > 0
