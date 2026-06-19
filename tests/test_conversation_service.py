"""Unit tests for pure-function parts of services/conversation_service.py."""
import pytest
from datetime import date, timedelta


@pytest.fixture(scope="module")
def svc():
    from services.conversation_service import ConversationService
    return ConversationService()


class TestCalculateDurationDays:
    def test_far_past_date_returns_large_positive(self, svc):
        result = svc.calculate_duration_days("2020-01-01")
        assert result > 365

    def test_today_returns_zero_or_one(self, svc):
        today = date.today().strftime("%Y-%m-%d")
        assert 0 <= svc.calculate_duration_days(today) <= 1

    def test_one_year_ago_approx_365(self, svc):
        one_year_ago = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
        result = svc.calculate_duration_days(one_year_ago)
        assert 360 <= result <= 370

    def test_future_date_returns_negative(self, svc):
        future = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        assert svc.calculate_duration_days(future) < 0

    def test_invalid_date_string_returns_zero(self, svc):
        assert svc.calculate_duration_days("not-a-date") == 0

    def test_empty_string_returns_zero(self, svc):
        assert svc.calculate_duration_days("") == 0

    def test_wrong_format_returns_zero(self, svc):
        assert svc.calculate_duration_days("01/01/2020") == 0

    def test_none_value_returns_zero(self, svc):
        assert svc.calculate_duration_days(None) == 0


class TestConversationServiceStates:
    def test_states_dict_contains_all_keys(self, svc):
        expected = {"inicio", "evaluacion", "profundizacion", "derivacion", "agendar_cita", "fin"}
        assert expected == set(svc.states.keys())

    def test_fin_state_is_none(self, svc):
        assert svc.states["fin"] is None

    def test_ai_service_is_not_none(self, svc):
        assert svc.ai_service is not None
