"""Milestone 2 small fixes: the lowest card counts today, and "next month" means next month."""

from datetime import date, timedelta

from aheadly.ai.llm_client import StubClient
from aheadly.domain import ForecastPoint, ForecastResult
from tests.conftest import TODAY


def _forecast(opening: float, base: float) -> ForecastResult:
    start = date(2026, 11, 10)
    points = [ForecastPoint(start + timedelta(days=i), base - 500, base, base + 500, 0.0) for i in range(3)]
    return ForecastResult(opening_balance=opening, points=points, model="test")


def test_lowest_is_today_when_nothing_ahead_is_lower():
    assert _forecast(opening=8200, base=8557).lowest_with_today() == (8200, None)


def test_lowest_is_ahead_when_the_forecast_dips():
    value, when = _forecast(opening=8200, base=-1497).lowest_with_today()
    assert value == -1497
    assert when == date(2026, 11, 10)


def test_next_month_question_asks_for_the_forecast_until_end_of_next_month():
    call = StubClient(TODAY).plan("Will I have enough cash next month?")
    assert call.name == "get_forecast"
    assert call.arguments == {"until": "2026-12-31"}


def test_next_month_answer_stays_inside_next_month(connected_core):
    data = connected_core.forecast_summary(until="2026-12-31")
    assert date.fromisoformat(data["lowest_point"]["date"]) <= date(2026, 12, 31)

    answer = connected_core.ask("Will I have enough cash next month?")
    assert "2026-12-31" in answer.text
