from datetime import date, timedelta

from aheadly.core import alert_rules
from aheadly.domain import Alert, Business, ForecastPoint, ForecastResult
from tests.conftest import TODAY

BUSINESS = Business(1, "Test", "Owner", "Bogotá", low_cash_line=2000)


def _forecast(p50_by_day: list[float], p10_offset: float = -500) -> ForecastResult:
    points = [
        ForecastPoint(TODAY + timedelta(days=i), v + p10_offset, v, v + 500, 0.0)
        for i, v in enumerate(p50_by_day)
    ]
    return ForecastResult(opening_balance=p50_by_day[0], points=points, model="test")


def test_shortfall_alert_raised_five_weeks_ahead():
    values = [8000.0] * 56
    values[32] = -4000.0
    facts = alert_rules.detect_shortfall(_forecast(values), BUSINESS, TODAY)
    assert facts is not None and facts.weeks_ahead == 5 and facts.severity == "high"
    assert facts.facts["lowest_balance"] == -4000


def test_no_shortfall_when_balance_stays_above_line():
    assert alert_rules.detect_shortfall(_forecast([5000.0] * 56), BUSINESS, TODAY) is None


def test_severity_bands():
    assert alert_rules.severity_for(1, 500) == "high"
    assert alert_rules.severity_for(4, 500) == "medium"
    assert alert_rules.severity_for(7, 500) == "low"


def test_idle_cash_when_worst_case_exceeds_three_months_of_outflows():
    forecast = _forecast([50000.0] * 56)
    assert (
        alert_rules.detect_idle_cash(forecast, BUSINESS, avg_monthly_outflow=10000, today=TODAY) is not None
    )
    assert alert_rules.detect_idle_cash(forecast, BUSINESS, avg_monthly_outflow=20000, today=TODAY) is None


def test_duplicate_alert_within_three_days_is_detected():
    existing = [Alert(1, "shortfall", "medium", 5, "t", "b", [], {"lowest_date": "2026-12-15"}, "")]
    new = alert_rules.AlertFacts("shortfall", "medium", 5, date(2026, 12, 17), {})
    far = alert_rules.AlertFacts("shortfall", "medium", 6, date(2026, 12, 25), {})
    assert alert_rules.find_duplicate(existing, new) is not None
    assert alert_rules.find_duplicate(existing, far) is None
