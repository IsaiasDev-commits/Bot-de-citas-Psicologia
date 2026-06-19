"""Unit tests for services/ai_service.py — no Groq API key required."""
import pytest


# ---------------------------------------------------------------------------
# Module-level fixtures to avoid class-scope deprecation warning
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fallback_svc():
    from services.ai_service import FallbackAIService
    return FallbackAIService()


@pytest.fixture(scope="module")
def groq_svc():
    """GroqAIService instance with Groq HTTP client bypassed.

    We test only the pure helper methods (_determine_complexity, _clean_response)
    which need no HTTP connection.  Using object.__new__ lets us skip __init__
    and avoid the groq/httpx version incompatibility in the CI environment.
    """
    from services.ai_service import GroqAIService
    obj = object.__new__(GroqAIService)
    obj.api_key = "sk-test-dummy"
    obj.client = None
    obj.available_models = {
        "high_quality": "openai/gpt-oss-120b",
        "balanced": "llama-3.1-70b-versatile",
        "fast": "openai/gpt-oss-20b",
    }
    return obj


# ---------------------------------------------------------------------------
# FallbackAIService
# ---------------------------------------------------------------------------

class TestFallbackAIService:
    def test_known_symptom_ansiedad(self, fallback_svc):
        resp = fallback_svc.generate_response("Me siento mal", symptom="Ansiedad")
        assert isinstance(resp, str) and len(resp) > 10

    def test_known_symptom_tristeza(self, fallback_svc):
        resp = fallback_svc.generate_response("Estoy triste", symptom="Tristeza")
        assert isinstance(resp, str) and len(resp) > 10

    def test_unknown_symptom_uses_general_pool(self, fallback_svc):
        resp = fallback_svc.generate_response("texto", symptom="SintomaInexistente")
        assert isinstance(resp, str) and len(resp) > 10

    def test_no_symptom_uses_general_pool(self, fallback_svc):
        resp = fallback_svc.generate_response("texto")
        assert isinstance(resp, str) and len(resp) > 10

    def test_select_model_always_returns_fallback(self, fallback_svc):
        assert fallback_svc.select_model(100, "normal") == "fallback"
        assert fallback_svc.select_model(500, "crisis") == "fallback"


# ---------------------------------------------------------------------------
# GroqAIService._determine_complexity
# ---------------------------------------------------------------------------

class TestDetermineComplexity:
    def test_quiero_morir_is_crisis(self, groq_svc):
        assert groq_svc._determine_complexity("quiero morir") == "crisis"

    def test_suicidio_is_crisis(self, groq_svc):
        assert groq_svc._determine_complexity("pienso en el suicidio") == "crisis"

    def test_matarme_is_crisis(self, groq_svc):
        assert groq_svc._determine_complexity("quiero matarme ya") == "crisis"

    def test_no_puedo_mas_is_crisis(self, groq_svc):
        assert groq_svc._determine_complexity("no puedo más") == "crisis"

    def test_short_neutral_is_normal(self, groq_svc):
        assert groq_svc._determine_complexity("hola estoy bien", symptom=None) == "normal"

    def test_ansiedad_symptom_is_complejo(self, groq_svc):
        assert groq_svc._determine_complexity("me siento raro", symptom="Ansiedad") == "complejo"

    def test_depresion_symptom_is_complejo(self, groq_svc):
        assert groq_svc._determine_complexity("ok", symptom="Depresión") == "complejo"

    def test_long_text_is_at_least_complejo(self, groq_svc):
        long_text = "me siento " * 30  # >200 chars
        result = groq_svc._determine_complexity(long_text, symptom=None)
        assert result in ("complejo", "crisis")

    def test_crisis_overrides_normal_symptom(self, groq_svc):
        assert groq_svc._determine_complexity("quiero morir " * 3) == "crisis"


# ---------------------------------------------------------------------------
# GroqAIService._clean_response
# ---------------------------------------------------------------------------

class TestCleanResponse:
    def test_removes_bold_markdown(self, groq_svc):
        result = groq_svc._clean_response("**negrita** texto")
        assert "**" not in result and "negrita" in result

    def test_removes_italic_markdown(self, groq_svc):
        result = groq_svc._clean_response("*cursiva* texto")
        assert "*" not in result and "cursiva" in result

    def test_removes_heading_hash(self, groq_svc):
        result = groq_svc._clean_response("## Título\n\nContenido")
        assert "#" not in result and "Título" in result

    def test_removes_bullet_point(self, groq_svc):
        result = groq_svc._clean_response("• Punto uno")
        assert "•" not in result

    def test_removes_dash_list_marker(self, groq_svc):
        result = groq_svc._clean_response("- Elemento")
        assert result.strip() == "Elemento"

    def test_collapses_triple_newlines(self, groq_svc):
        result = groq_svc._clean_response("a\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_strips_surrounding_whitespace(self, groq_svc):
        assert groq_svc._clean_response("  texto  ") == "texto"

    def test_empty_string_returns_falsy(self, groq_svc):
        assert not groq_svc._clean_response("")

    def test_none_returns_falsy(self, groq_svc):
        assert not groq_svc._clean_response(None)

    def test_plain_text_preserves_content(self, groq_svc):
        text = "Hola, esto es un texto normal sin markdown."
        result = groq_svc._clean_response(text)
        assert "Hola" in result and len(result) > 0


# ---------------------------------------------------------------------------
# AIServiceFactory
# ---------------------------------------------------------------------------

class TestAIServiceFactory:
    def test_create_fallback_service(self):
        from services.ai_service import AIServiceFactory, FallbackAIService
        assert isinstance(AIServiceFactory.create_service("fallback"), FallbackAIService)

    def test_create_unknown_falls_back(self):
        from services.ai_service import AIServiceFactory, FallbackAIService
        assert isinstance(AIServiceFactory.create_service("unknown_xyz"), FallbackAIService)

    def test_get_instance_without_api_key_returns_fallback(self, monkeypatch):
        from services.ai_service import AIServiceFactory, FallbackAIService
        saved = AIServiceFactory._instance
        AIServiceFactory._instance = None
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        try:
            assert isinstance(AIServiceFactory.get_instance(), FallbackAIService)
        finally:
            AIServiceFactory._instance = saved

    def test_get_instance_is_singleton(self, monkeypatch):
        from services.ai_service import AIServiceFactory
        saved = AIServiceFactory._instance
        AIServiceFactory._instance = None
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        try:
            assert AIServiceFactory.get_instance() is AIServiceFactory.get_instance()
        finally:
            AIServiceFactory._instance = saved
