"""Roadmap 2.8: how much to trust the forecast, the "nothing big planned" note, and a band that
reflects payments that vary and stronger or weaker stretches."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from aheadly.ai import confidence
from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.models import SeasonalNaiveModel
from aheadly.domain import ScheduledItem
from tests.test_businesses import import_business


def test_levels_follow_the_weakest_checks():
    good = [confidence.history_check(365), confidence.statement_check(0), confidence.answers_check(5, 5)]
    assert confidence.level(good)["level"] == "high"
    one_weak = good + [confidence.statement_check(2)]
    result = confidence.level(one_weak)
    assert result["level"] == "medium" and "doesn't add up in 2 place" in result["reasons"][0]
    two_weak = one_weak + [confidence.history_check(40)]
    assert confidence.level(two_weak)["level"] == "low"


def test_a_broken_statement_line_shows_in_the_confidence():
    result = import_business("taller-los-pistones", with_one_offs=True).forecast_confidence()
    assert result["level"] == "medium"
    assert result["reasons"][0].startswith("The running balance doesn't add up in 1 place")


def test_answering_the_questions_raises_confidence():
    assert import_business("panaderia-la-esquina").forecast_confidence()["level"] == "medium"
    assert (
        import_business("panaderia-la-esquina", with_one_offs=True).forecast_confidence()["level"] == "high"
    )


def test_skipping_the_questions_is_not_answering_them():
    core = import_business("panaderia-la-esquina")
    for question in core.onboarding()["questions"]:
        core.skip_question(question.id)
    result = core.forecast_confidence()
    assert result["level"] == "medium"
    assert any("aren't answered yet" in reason for reason in result["reasons"])
    core.answer_seasons([12], [1])  # answered after all: it counts
    answers = next(c for c in core.forecast_confidence()["checks"] if c.name == "answers")
    assert answers.text.startswith("You answered 1 of ")


def test_the_note_appears_only_when_no_one_off_is_known():
    assert import_business("panaderia-la-esquina").no_one_offs_planned()
    assert not import_business("panaderia-la-esquina", with_one_offs=True).no_one_offs_planned()


def _flat(days=140, wobble=0.0):
    dates = pd.date_range("2026-06-01", periods=days, freq="D")
    level = np.repeat(np.random.default_rng(3).normal(0, wobble, days // 28 + 1), 28)[:days]
    return pd.DataFrame({"date": dates, "net_flow": 100.0 + level})


def test_a_payment_that_varies_widens_the_band():
    engine = ForecastEngine(SeasonalNaiveModel(), n_paths=400)
    fixed = ScheduledItem("Gas", -500, date(2026, 11, 5))
    moving = ScheduledItem("Gas", -500, date(2026, 11, 5), spread=0.3, jitter_days=2)
    a = engine.forecast(_flat(), 0, [fixed], date(2026, 11, 1), 14).points[-1]
    b = engine.forecast(_flat(), 0, [moving], date(2026, 11, 1), 14).points[-1]
    assert b.balance_p90 - b.balance_p10 > a.balance_p90 - a.balance_p10 + 200
    assert b.balance_p50 == pytest.approx(a.balance_p50, abs=60)


def test_a_business_with_uneven_months_gets_a_wider_band():
    engine = ForecastEngine(SeasonalNaiveModel(), n_paths=400)
    steady = engine.forecast(_flat(), 0, [], date(2026, 10, 19), 28).points[-1]
    uneven = engine.forecast(_flat(wobble=40), 0, [], date(2026, 10, 19), 28).points[-1]
    assert uneven.balance_p90 - uneven.balance_p10 > steady.balance_p90 - steady.balance_p10 + 1000


def test_a_payment_the_owner_set_has_no_spread():
    core = import_business("panaderia-la-esquina")
    moved = core._how_items_moved()
    utilities = next(i for i in core.repo.list_scheduled_items(core._business().id) if i.id in moved)
    core.update_plan_item(utilities.id, amount=abs(utilities.amount))
    assert core._how_items_moved().get(utilities.id, (0.0, 0))[0] == 0.0
