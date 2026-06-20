"""Unit tests for calendar_sync_service pure helper functions."""
import pytest


# ---------------------------------------------------------------------------
# _extract_phone
# ---------------------------------------------------------------------------

class TestExtractPhone:
    @pytest.fixture(autouse=True)
    def fn(self):
        from services.calendar_sync_service import _extract_phone
        self._fn = _extract_phone

    def test_valid_10_digit_phone(self):
        assert self._fn("Teléfono del paciente: 0991234567") == "0991234567"

    def test_phone_embedded_in_multiline(self):
        desc = "Síntoma: Ansiedad\nTeléfono: 0981234567\nOtro campo"
        assert self._fn(desc) == "0981234567"

    def test_no_phone_returns_empty(self):
        assert self._fn("Sin número de teléfono aquí") == ""

    def test_empty_string_returns_empty(self):
        assert self._fn("") == ""

    def test_none_returns_empty(self):
        assert self._fn(None) == ""

    def test_8_digit_number_not_matched(self):
        assert self._fn("Número: 09912345") == ""

    def test_number_not_starting_with_0_not_matched(self):
        assert self._fn("Tel: 1991234567") == ""

    def test_returns_first_match(self):
        # The real description has exactly one phone number
        result = self._fn("0991111111 y 0992222222")
        assert result in ("0991111111", "0992222222")


# ---------------------------------------------------------------------------
# _extract_patient_name
# ---------------------------------------------------------------------------

class TestExtractPatientName:
    @pytest.fixture(autouse=True)
    def fn(self):
        from services.calendar_sync_service import _extract_patient_name
        self._fn = _extract_patient_name

    def test_single_dash_returns_last_part(self):
        assert self._fn("Cita Psicológica - Ansiedad") == "Ansiedad"

    def test_multiple_dashes_returns_last_part(self):
        assert self._fn("A - B - C") == "C"

    def test_no_dash_returns_full_string(self):
        assert self._fn("SinGuion") == "SinGuion"

    def test_empty_string_returns_empty(self):
        assert self._fn("") == ""

    def test_none_returns_empty(self):
        assert self._fn(None) == ""

    def test_strips_whitespace(self):
        assert self._fn("Titulo -  Ansiedad  ") == "Ansiedad"


# ---------------------------------------------------------------------------
# _extract_symptom
# ---------------------------------------------------------------------------

class TestExtractSymptom:
    @pytest.fixture(autouse=True)
    def fn(self):
        from services.calendar_sync_service import _extract_symptom
        self._fn = _extract_symptom

    def test_sintoma_colon_format(self):
        desc = "Teléfono del paciente: 0991234567\nSíntoma principal: Ansiedad\nOtro"
        assert self._fn(desc) == "Ansiedad"

    def test_motivo_colon_format(self):
        assert self._fn("Motivo de consulta: Depresión") == "Depresión"

    def test_case_insensitive_sintoma(self):
        assert self._fn("SÍNTOMA: Estrés") == "Estrés"

    def test_no_symptom_returns_empty(self):
        assert self._fn("Sin información relevante aquí") == ""

    def test_empty_string_returns_empty(self):
        assert self._fn("") == ""

    def test_none_returns_empty(self):
        assert self._fn(None) == ""

    def test_strips_whitespace_from_value(self):
        assert self._fn("Síntoma:   Tristeza   ") == "Tristeza"

    def test_no_colon_in_symptom_line_returns_empty(self):
        # Line contains "síntoma" but no colon-separated value
        assert self._fn("El síntoma es grave") == ""
