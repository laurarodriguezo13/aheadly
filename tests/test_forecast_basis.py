"""Roadmap 2.6: the "How we built your forecast" page. Everything the forecast counts on, each
piece editable, and the effect of each change shown."""

from datetime import date, timedelta

import pandas as pd
import pytest

from aheadly.ai import recurring
from aheadly.ai.forecast_engine import ForecastEngine, SeasonalNaiveModel, expand_scheduled_items
from aheadly.domain import ScheduledItem
from tests.test_example_business import DAY_AFTER_STATEMENT, _core


@pytest.fixture(scope="module")
def bakery():
    core = _core()
    core.load_example()
    return core


def _fresh():
    core = _core()
    core.load_example()
    return core


def _item(core, label_start: str) -> dict:
    basis = core.forecast_basis()
    return next(r for r in basis["regular"] + basis["one_offs"] if r["label"].startswith(label_start))


# ------------------------------------------------------------- what the page shows
def test_the_page_lists_where_it_starts_the_rhythm_and_every_payment(bakery):
    basis = bakery.forecast_basis()
    start = basis["start"]
    assert start["balance"] == pytest.approx(8200)
    assert start["statement_end"] == date(2026, 11, 10)
    assert start["transactions"] > 1000
    rhythm = basis["rhythm"]
    assert rhythm["in_low"] <= rhythm["in_high"] and rhythm["busiest_day"] == "Saturday"
    labels = [r["label"] for r in basis["regular"]]
    assert "Pago arriendo local" in labels and "Pago nomina" in labels
    assert [r["label"] for r in basis["one_offs"]][:2] == ["Corporate hamper order", "New oven"]


def test_each_payment_says_where_it_came_from_and_how_often(bakery):
    rent = _item(bakery, "Pago arriendo local")
    assert rent["badge"] == "statement" and rent["how_often"] == "monthly on the 15th"
    assert rent["next"] == date(2026, 11, 16)  # the 15th is a Sunday
    assert _item(bakery, "New oven")["badge"] == "example"
    assert _item(bakery, "Overdue invoice")["maybe"]


def test_next_month_adds_up_to_the_forecast(bakery):
    month = bakery.forecast_basis()["next_month"]
    forecast = bakery.get_dashboard().forecast
    days = [p for p in forecast.points if month["first"] <= p.date <= month["last"]]
    total = sum(p.net_flow_p50 for p in days)
    parts = ("rhythm", "recurring_in", "recurring_out", "one_off_in", "one_off_out")
    assert sum(month[k] for k in parts) == pytest.approx(total, abs=0.05)
    assert month["one_off_out"] == pytest.approx(-6640)  # Christmas ingredients + the flour order, once


@pytest.mark.parametrize(
    "rule, due, text",
    [
        ("weekly", date(2026, 11, 13), "weekly (Fridays)"),
        ("biweekly", date(2026, 11, 13), "every two weeks (Fridays)"),
        ("month_day:last_bd:prev:1", date(2026, 11, 30), "monthly on the last business day"),
        ("month_day:15:next:3", date(2026, 12, 15), "quarterly on the 15th"),
        ("month_day:2:next:2", date(2026, 12, 2), "every 2 months on the 2nd"),
        ("every:35", date(2026, 12, 2), "about every 35 days"),
        (None, date(2026, 12, 2), "once"),
    ],
)
def test_how_often_in_plain_words(rule, due, text):
    assert recurring.describe(rule, due) == text


# ------------------------------------------------------------- editing it
def test_editing_a_found_payment_changes_the_forecast_and_shows_the_effect():
    core = _fresh()
    flour = _item(core, "Pago pse molinos")
    effect = core.update_plan_item(flour["id"], amount=abs(flour["amount"]) * 2)
    assert effect["after"] < effect["before"]  # a bigger expense: a lower lowest balance
    edited = _item(core, "Pago pse molinos")
    assert edited["amount"] == pytest.approx(flour["amount"] * 2)  # stays money out
    assert edited["badge"] == "confirmed"


def test_an_edited_payment_survives_a_new_upload_of_the_statement():
    core = _fresh()
    rent = _item(core, "Pago arriendo local")
    core.update_plan_item(rent["id"], amount=950)
    core._detect_recurring(core._business().id)
    after = [r for r in core.forecast_basis()["regular"] if r["label"] == "Pago arriendo local"]
    assert len(after) == 1 and after[0]["amount"] == pytest.approx(-950)


def test_no_suggestion_right_after_the_owner_sets_an_amount():
    core = _fresh()
    rent = _item(core, "Pago arriendo local")
    core.update_plan_item(rent["id"], amount=800)
    assert core.forecast_basis()["suggestions"] == []


def test_a_newer_statement_with_a_different_amount_is_suggested_not_applied():
    core = _fresh()
    rent = _item(core, "Pago arriendo local")
    core.update_plan_item(rent["id"], amount=800)
    seen = {str(rent["id"]): "2026-10-10"}  # as if the owner set it with last month's statement
    core.repo.save_profile(core._business().id, {"amount_set_with_statement": seen})
    suggestion = core.forecast_basis()["suggestions"]
    assert suggestion == [
        {"id": rent["id"], "label": "Pago arriendo local", "planned": -800.0, "found": -900.0}
    ]
    assert _item(core, "Pago arriendo local")["amount"] == pytest.approx(-800)


def test_pausing_ending_and_removing():
    core = _fresh()
    payroll = _item(core, "Pago nomina")
    paused = core.pause_plan_item(payroll["id"])
    assert paused["after"] > paused["before"]
    assert core.forecast_basis()["not_counted"]["paused"] == ["Pago nomina"]
    resumed = core.pause_plan_item(payroll["id"], paused=False)
    assert resumed["after"] == paused["before"]
    ended = core.end_plan_item(payroll["id"], DAY_AFTER_STATEMENT + timedelta(days=13))
    assert ended["before"] < ended["after"] < paused["after"]  # two more paydays still counted
    removed = core.delete_plan_item(payroll["id"])
    assert removed["after"] == paused["after"]
    gone = core.forecast_basis()["not_counted"]["switched_off"]
    assert gone == [{"label": "Pago nomina", "amount": payroll["amount"], "why": "removed"}]


def test_confirming_a_found_payment_does_not_change_the_forecast():
    core = _fresh()
    before = core.get_dashboard().forecast.lowest_with_today()[0]
    flour = _item(core, "Pago pse molinos")
    core.confirm_plan_item(flour["id"])
    core.run_daily_check(force=True)
    assert core.get_dashboard().forecast.lowest_with_today()[0] == pytest.approx(before)
    assert _item(core, "Pago pse molinos")["badge"] == "confirmed"


def test_adding_a_one_off_lowers_the_lowest_balance():
    core = _fresh()
    before = core.get_dashboard().forecast.lowest_with_today()[0]
    core.add_plan_items(
        [{"label": "Van repair", "amount": 3000, "direction": "out", "due_date": "2026-11-20"}]
    )
    after = core.get_dashboard().forecast.lowest_with_today()[0]
    assert after == pytest.approx(before - 3000, abs=1)


def test_an_item_that_is_gone_says_so():
    core = _fresh()
    with pytest.raises(ValueError, match="isn't in your plan"):
        core.update_plan_item(99999, amount=5)


# ------------------------------------------------------------- the engine
def test_paused_and_ended_items_expand_correctly():
    weekly = ScheduledItem("Cleaner", -50, date(2026, 11, 13), recurrence="weekly")
    end = date(2026, 12, 31)
    assert len(expand_scheduled_items([weekly], date(2026, 11, 11), end)) == 7
    assert (
        expand_scheduled_items(
            [ScheduledItem(**{**weekly.__dict__, "paused": True})], date(2026, 11, 11), end
        )
        == []
    )
    ended = ScheduledItem(**{**weekly.__dict__, "end_date": date(2026, 11, 27)})
    assert len(expand_scheduled_items([ended], date(2026, 11, 11), end)) == 3


def _flat_history(days: int = 60) -> pd.DataFrame:
    dates = pd.date_range(date(2026, 9, 1), periods=days, freq="D")
    return pd.DataFrame({"date": dates, "net_flow": [0.0] * days})


def test_maybe_income_arrives_in_only_some_paths_and_maybe_expenses_in_all():
    engine = ForecastEngine(SeasonalNaiveModel(), n_paths=400)
    start = date(2026, 11, 1)
    maybe_in = ScheduledItem("Maybe client", 1000, date(2026, 11, 5), certainty="maybe")
    maybe_out = ScheduledItem("Maybe repair", -1000, date(2026, 11, 5), certainty="maybe")
    with_income = engine.forecast(_flat_history(), 0, [maybe_in], start, 14).points[-1]
    assert with_income.balance_p10 == pytest.approx(0, abs=1)  # some paths: it never came
    assert with_income.balance_p90 == pytest.approx(1000, abs=1)  # others: it did
    with_expense = engine.forecast(_flat_history(), 0, [maybe_out], start, 14).points[-1]
    assert with_expense.balance_p90 == pytest.approx(-1000, abs=1)  # counted in every path
