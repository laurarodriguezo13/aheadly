"""Roadmap 3.1: the chance of dipping below the low cash line.

Each of the forecast's paths is one way the coming weeks could go. The chance is the share of paths
whose balance goes below the line on at least one day (today's balance counts too). It is computed
from the run's paths, saved with the run, and given to the alert, the chat and the what-if result.
"""

from datetime import date, timedelta

import numpy as np

from aheadly.ai import templates
from aheadly.ai.guardrails import check_numbers
from aheadly.domain import ForecastPoint, ForecastResult, end_of_next_month
from aheadly.ui import copy
from tests.conftest import TODAY

START = date(2026, 11, 11)


def _result(paths: list[list[float]], opening: float) -> ForecastResult:
    balances = np.array(paths, dtype=float)
    p10, p50, p90 = np.percentile(balances, [10, 50, 90], axis=0)
    points = [
        ForecastPoint(START + timedelta(days=i), p10[i], p50[i], p90[i], 0.0)
        for i in range(balances.shape[1])
    ]
    return ForecastResult(opening, points, "test", balance_paths=balances)


def test_chance_is_the_share_of_paths_that_dip_below_the_line():
    result = _result([[5000, 1500, 4000], [5000, 4000, 4000], [5000, 4500, 1900], [5000, 6000, 7000]], 5000)
    assert result.chance_below(2000) == 0.5  # two of four paths dip, on different days
    assert result.chance_below(1000) == 0.0
    assert result.chance_below(10_000) == 1.0


def test_only_days_up_to_a_date_count_when_asked():
    result = _result([[5000, 4000, 1500], [5000, 4000, 4000]], 5000)
    assert result.chance_below(2000) == 0.5
    assert result.chance_below(2000, until=START + timedelta(days=1)) == 0.0


def test_today_below_the_line_is_certain():
    result = _result([[5000, 6000], [5000, 6000]], opening=1500)
    assert result.chance_below(2000) == 1.0


def test_chance_agrees_with_the_risk_level(connected_core):
    """act_now (the middle path dips) means at least half the paths dip on that day; watch (the worst
    10% dip) means at least one in ten. The chance can only be higher than that, never lower."""
    forecast = connected_core._baseline_forecast()
    line = connected_core.status().business.low_cash_line
    chance = forecast.chance_below(line)
    assert 0 <= chance <= 1
    level = forecast.risk_level(line)
    if level == "act_now":
        assert chance >= 0.5
    elif level == "watch":
        assert chance >= 0.1


def test_engine_keeps_every_path(connected_core):
    forecast = connected_core._baseline_forecast()
    assert forecast.balance_paths.shape == (connected_core.engine.n_paths, len(forecast.points))
    middle = np.median(forecast.balance_paths, axis=0)
    assert abs(middle[-1] - forecast.points[-1].balance_p50) < 1e-6


def test_chance_is_saved_with_the_run(connected_core):
    line = connected_core.status().business.low_cash_line
    connected_core.run_daily_check(force=True)
    fresh = connected_core._baseline_forecast().chance_below(line)
    stored = connected_core.get_dashboard().forecast  # read back from the database, without the paths
    assert stored.balance_paths is None
    assert stored.chance_below(line) == fresh


def test_alert_facts_carry_the_chance_and_the_text_says_it(connected_core):
    connected_core.run_daily_check(force=True)
    shortfall = [a for a in connected_core.get_alerts() if a.type == "shortfall"]
    assert shortfall, "the seeded bakery has a shortfall"
    facts = shortfall[0].facts
    assert 50 <= facts["chance_below_line_pct"] <= 100
    text = templates.alert_text(facts)
    assert text["body"].endswith(templates.chance_sentence(facts["chance_below_line_pct"]))
    assert check_numbers(f"{text['title']} {text['body']}", [facts]).passed


def test_chat_and_what_if_numbers_include_the_chance(connected_core):
    summary = connected_core.forecast_summary()
    assert 0 <= summary["chance_below_line_pct"] <= 100
    result = connected_core.run_what_if(
        [{"type": "one_time_expense", "amount": 3000, "date": (TODAY + timedelta(days=9)).isoformat()}]
    )
    numbers = result.summary()
    assert "chance_below_line_pct" in numbers["baseline"]
    assert numbers["scenario"]["chance_below_line_pct"] >= numbers["baseline"]["chance_below_line_pct"]


def test_chance_in_plain_words():
    assert copy.chance_words(64) == "64% chance of dipping below your line"
    assert copy.chance_words(0) == "no scenario dips below your line"
    assert copy.chance_words(100) == "every scenario dips below your line"
    assert copy.chance_words(None) == ""


def test_a_payment_that_moves_later_lowers_the_chance(connected_core):
    """Moving the oven to next month (the canonical demo) makes dipping below the line unlikely."""
    business_id = connected_core.status().business.id
    oven = next(i for i in connected_core.repo.list_scheduled_items(business_id) if "oven" in i.label.lower())
    later = end_of_next_month(TODAY)
    result = connected_core.run_what_if(
        [{"type": "move_item", "label": oven.label, "new_date": later.isoformat()}]
    )
    numbers = result.summary()
    assert numbers["baseline"]["chance_below_line_pct"] >= 90
    assert numbers["scenario"]["chance_below_line_pct"] <= 10


def test_chat_answers_without_the_model_say_the_chance(connected_core):
    answer = connected_core.ask("Will I have enough cash next month?")
    assert answer.text.endswith(
        templates.chance_clause(
            connected_core.forecast_summary(until=end_of_next_month(TODAY).isoformat())[
                "chance_below_line_pct"
            ]
        )
    )


def test_chance_below_is_calibrated_overall():
    """Across the six test businesses, the squared gap between the chance and what really happened
    (1 = the balance went below the line, 0 = it didn't) averages well under 0.25, what always
    saying 50% would score. The per-business check is in tests/test_businesses.py."""
    from tests.test_businesses import KEYS, _chance, _really_dipped

    gaps = [(_chance(slug) - _really_dipped(key)) ** 2 for slug, key in KEYS.items()]
    assert sum(gaps) / len(gaps) < 0.10


def test_none_and_every_are_always_true():
    """Rounding never turns a small chance into "none" or a large one into "every" (seen in the
    browser: "about 0%" and "About 100% of the ways")."""
    from aheadly.domain import chance_pct

    assert chance_pct(0.003) == 1 and chance_pct(0.998) == 99
    assert chance_pct(0.0) == 0 and chance_pct(1.0) == 100 and chance_pct(None) is None
    assert templates.chance_clause(0) == " None of the ways the coming weeks could go dips below your line."
    assert templates.chance_sentence(100) == " Every way the coming weeks could go dips below it."
    assert "about 64%" in templates.chance_clause(64)
