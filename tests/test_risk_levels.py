"""Verdicts use the worst case too: act now / keep an eye on it / safe."""

from datetime import date, timedelta

from aheadly.ai.templates import answer_from_tool
from aheadly.domain import ForecastPoint, ForecastResult


def _forecast(worst: float, base: float) -> ForecastResult:
    start = date(2026, 11, 10)
    points = [ForecastPoint(start + timedelta(days=i), worst, base, base + 1000, 0.0) for i in range(3)]
    return ForecastResult(opening_balance=8200, points=points, model="test")


def test_act_now_when_base_case_drops_below_line():
    assert _forecast(worst=-500, base=1500).risk_level(2000) == "act_now"


def test_watch_when_only_worst_case_drops_below_line():
    assert _forecast(worst=479, base=6500).risk_level(2000) == "watch"


def test_safe_when_worst_case_stays_above_line():
    assert _forecast(worst=2600, base=6000).risk_level(2000) == "safe"


def test_watch_scenario_is_never_called_safe():
    data = {
        "scenario": {
            "lowest_base_case": 6557,
            "lowest_date": "2027-01-04",
            "lowest_worst_case": 479,
            "lowest_best_case": 9627,
        },
        "low_cash_line": 2000,
        "stays_above_low_cash_line": True,
        "risk_level": "watch",
    }
    text = answer_from_tool("run_scenario", data).lower()
    assert "safe" not in text
    assert "keep an eye" in text


def test_canonical_story_act_now_then_safe_after_moving_oven(connected_core):
    dash = connected_core.get_dashboard()
    assert dash.forecast.risk_level(dash.business.low_cash_line) == "act_now"

    result = connected_core.run_what_if(
        [{"type": "move_item", "label": "oven", "new_date": "2026-12-31"}], "Oven next month"
    )
    assert result.summary()["risk_level"] == "safe"
