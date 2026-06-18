"""Tests para constants.py — crisis detection y lista de síntomas."""
import pytest
from constants import detectar_crisis, SINTOMAS_DISPONIBLES, CRISIS_RESPONSE


class TestDetectarCrisis:
    def test_suicidio_detectado(self):
        assert detectar_crisis("quiero suicidio") is True

    def test_matarme_detectado(self):
        assert detectar_crisis("quiero matarme ya") is True

    def test_autolesion_detectado(self):
        assert detectar_crisis("me hago autolesión") is True

    def test_texto_normal_no_crisis(self):
        assert detectar_crisis("me siento triste hoy") is False

    def test_texto_vacio_no_crisis(self):
        assert detectar_crisis("") is False

    def test_case_insensitive(self):
        assert detectar_crisis("SUICIDIO") is True

    def test_crisis_response_no_vacia(self):
        assert isinstance(CRISIS_RESPONSE, str) and len(CRISIS_RESPONSE) > 10


class TestSintomasDisponibles:
    def test_lista_no_vacia(self):
        assert len(SINTOMAS_DISPONIBLES) > 0

    def test_ansiedad_incluida(self):
        assert "Ansiedad" in SINTOMAS_DISPONIBLES

    def test_tristeza_incluida(self):
        assert "Tristeza" in SINTOMAS_DISPONIBLES

    def test_todos_son_strings(self):
        for s in SINTOMAS_DISPONIBLES:
            assert isinstance(s, str) and len(s) > 0

    def test_no_hay_duplicados(self):
        assert len(SINTOMAS_DISPONIBLES) == len(set(SINTOMAS_DISPONIBLES))
