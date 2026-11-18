"""Issue 20: "move it to next month" without a day. Code tries every weekday of next month and keeps
the earliest one that gets the best result, instead of a fixed day (the model picked the end of the
month, the tool description said the same day next month)."""

from __future__ import annotations

from datetime import date

from aheadly.ai import prompts, templates
from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import StubClient
from aheadly.ai.models import SeasonalNaiveModel
from aheadly.ai.tools import ADJUSTMENT_SCHEMA
from aheadly.config import Settings
from aheadly.core import actions
from aheadly.core.app_core import AppCore
from aheadly.data.repository import Repository
from aheadly.domain import NEXT_MONTH

EXAMPLE_TODAY = date(2026, 11, 11)


def _example() -> AppCore:
    core = AppCore(
        Repository(":memory:"),
        ForecastEngine(SeasonalNaiveModel(), n_paths=300),
        Settings(llm_provider="stub", db_path=":memory:"),
        llm=StubClient(EXAMPLE_TODAY),
        today=EXAMPLE_TODAY,
    )
    core.load_example()
    return core


def test_offline_chat_leaves_the_day_to_code():
    call = StubClient(EXAMPLE_TODAY).plan("What if I move the new oven payment to next month?", ["New oven"])
    assert call.arguments["adjustments"][0]["new_date"] == NEXT_MONTH


def test_a_day_the_owner_names_is_kept():
    call = StubClient(EXAMPLE_TODAY).plan("What if I move the new oven payment to Dec 20?", ["New oven"])
    assert call.arguments["adjustments"][0]["new_date"] == "2026-12-20"


def test_pick_day_keeps_the_earliest_day_with_the_best_status():
    tried = [
        (date(2026, 12, 1), "act_now", -1500),
        (date(2026, 12, 16), "safe", 3880),
        (date(2026, 12, 17), "safe", 4100),
        (date(2026, 12, 31), "safe", 6058),
    ]
    assert actions.pick_day(tried) == (date(2026, 12, 16), "earliest_above_line")


def test_pick_day_without_a_safe_day_keeps_the_highest_lowest_balance():
    tried = [
        (date(2026, 12, 1), "act_now", -1500),
        (date(2026, 12, 10), "act_now", -200),
        (date(2026, 12, 31), "act_now", -900),
    ]
    assert actions.pick_day(tried) == (date(2026, 12, 10), "highest_lowest_balance")


def test_moving_the_oven_to_next_month_picks_the_earliest_day_that_works():
    core = _example()
    answer = core.ask("What if I move the new oven payment to next month?")
    result = answer.scenario
    moved = result.adjustments[0].params["new_date"]
    assert moved.month == 12 and moved.weekday() < 5
    assert result.stays_above_line
    picked = result.summary()["picked_day"]
    assert picked["day"] == moved.isoformat() and picked["why"] == "earliest_above_line"
    # every earlier weekday of December leaves the bakery below its line
    earlier = core._scenario(
        [{"type": "move_item", "label": "New oven", "new_date": date(2026, 12, moved.day - 1).isoformat()}]
    )
    assert not earlier.stays_above_line or date(2026, 12, moved.day - 1).weekday() >= 5
    assert f"{moved:%b} {moved.day}" in answer.text
    assert result.name == f"Move New oven to {moved:%b} {moved.day}"


def test_the_words_say_which_day_and_why():
    data = {
        "risk_level": "safe",
        "low_cash_line": 2000,
        "scenario": {
            "lowest_base_case": 3880,
            "lowest_date": "2026-12-16",
            "lowest_worst_case": 2900,
            "lowest_best_case": 4800,
            "chance_below_line_pct": 1,
        },
        "picked_day": {
            "label": "New oven",
            "day": "2026-12-16",
            "why": "earliest_above_line",
            "days_tried": 23,
        },
    }
    text = templates.answer_from_tool("run_scenario", data)
    assert "Dec 16" in text and "23" in text and "earliest" in text


def test_the_model_is_told_to_leave_the_day_to_code():
    assert "end of next month" not in ADJUSTMENT_SCHEMA["properties"]["new_date"]["description"].lower()
    assert NEXT_MONTH in ADJUSTMENT_SCHEMA["properties"]["new_date"]["description"]
    assert NEXT_MONTH in prompts.CHAT_SYSTEM_PROMPT
    assert "picked_day" in prompts.CHAT_SYSTEM_PROMPT
