"""Tests de integración para las rutas HTTP principales de Equilibra."""
import json
import pytest


class TestHealthCheck:
    def test_health_retorna_200_o_503(self, client):
        r = client.get("/health")
        assert r.status_code in (200, 503)

    def test_health_json_valido(self, client):
        r = client.get("/health")
        data = r.get_json()
        assert "status" in data
        assert "services" in data

    def test_health_campos_servicios(self, client):
        r = client.get("/health")
        data = r.get_json()
        for key in ("groq", "email", "calendar", "database"):
            assert key in data["services"]


class TestRobotsAndSitemap:
    def test_robots_txt_accesible(self, client):
        r = client.get("/robots.txt")
        assert r.status_code == 200
        assert b"User-agent" in r.data

    def test_robots_bloquea_admin(self, client):
        r = client.get("/robots.txt")
        assert b"/admin/" in r.data

    def test_sitemap_xml_accesible(self, client):
        r = client.get("/sitemap.xml")
        assert r.status_code == 200
        assert b"urlset" in r.data


class TestSecurityHeaders:
    def test_x_frame_options(self, client):
        r = client.get("/health")
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options(self, client):
        r = client.get("/health")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_csp_presente(self, client):
        r = client.get("/health")
        csp = r.headers.get("Content-Security-Policy", "")
        assert "default-src" in csp
        assert "frame-ancestors" in csp


class TestAgendarCitaValidacion:
    def test_datos_incompletos_retorna_400(self, client):
        r = client.post(
            "/agendar-cita",
            data=json.dumps({"fecha": "2026-07-01"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_sintoma_invalido_retorna_400(self, client):
        r = client.post(
            "/agendar-cita",
            data=json.dumps({
                "fecha": "2026-07-01",
                "hora": "10:00",
                "telefono": "0991234567",
                "sintoma": "Sintoma_que_no_existe_xyzabc",
            }),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_sin_body_retorna_400(self, client):
        r = client.post("/agendar-cita", content_type="application/json")
        assert r.status_code == 400


class TestVerificarHorario:
    def test_sin_datos_retorna_400(self, client):
        r = client.post(
            "/verificar-horario",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_formato_invalido_retorna_400(self, client):
        r = client.post(
            "/verificar-horario",
            data=json.dumps({"fecha": "no-fecha", "hora": "10:00"}),
            content_type="application/json",
        )
        assert r.status_code == 400


class TestPing:
    def test_ping_200(self, client):
        r = client.get("/ping")
        assert r.status_code == 200

    def test_ping_json(self, client):
        r = client.get("/ping")
        assert r.get_json() == {"ok": True}

    def test_ping_rapido_sin_db(self, client):
        """Verifica que /ping no depende de la DB."""
        r = client.get("/ping")
        assert r.status_code == 200


class TestReset:
    def test_reset_get_no_permitido(self, client):
        r = client.get("/reset")
        assert r.status_code == 405

    def test_reset_post_retorna_json(self, client):
        r = client.post("/reset")
        assert r.content_type.startswith("application/json")


class TestCancelarCita:
    def test_cancelar_get_no_permitido(self, client):
        r = client.get("/cancelar_cita")
        assert r.status_code == 405

    def test_cancelar_post_retorna_success(self, client):
        r = client.post("/cancelar_cita")
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "success"


class TestObtenerHorariosDisponibles:
    def test_sin_body_retorna_400(self, client):
        r = client.post("/obtener-horarios-disponibles", content_type="application/json")
        assert r.status_code == 400

    def test_sin_fecha_retorna_400(self, client):
        r = client.post(
            "/obtener-horarios-disponibles",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_fecha_invalida_retorna_400(self, client):
        r = client.post(
            "/obtener-horarios-disponibles",
            data=json.dumps({"fecha": "no-es-fecha"}),
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_fecha_valida_retorna_lista(self, client):
        r = client.post(
            "/obtener-horarios-disponibles",
            data=json.dumps({"fecha": "2027-06-15"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_domingo_retorna_lista_vacia(self, client):
        r = client.post(
            "/obtener-horarios-disponibles",
            data=json.dumps({"fecha": "2027-06-13"}),  # domingo
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.get_json() == []
