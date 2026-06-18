"""Tests para ValidationService — teléfono, fechas y horarios de citas."""
import pytest
from datetime import date, timedelta
from services.validation_service import ValidationService


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
