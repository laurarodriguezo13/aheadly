"""Roadmap R.1: polish after Miguel's review of the app (badge, more alerts, below zero, chat)."""

import sqlite3

import pytest

from aheadly.ai import templates
from aheadly.ai.guardrails import check_numbers
from aheadly.ai.llm_client import StubClient, best_label
from aheadly.core.onboarding import fits_direction
from aheadly.data.repository import MIGRATIONS, SCHEMA_PATH, Repository
from aheadly.ui.copy import risk_name
from tests.conftest import TODAY
from tests.test_businesses import import_business

LABELS = ["New oven", "Quarterly flour order (Molinos del Sur)", "Christmas ingredients"]


@pytest.fixture(scope="module")
def bakery():
    return import_business("panaderia-la-esquina", with_one_offs=True)


@pytest.fixture(scope="module")
def costume():
    return import_business("disfraces-la-fantasia", with_one_offs=True)


# ------------------------------------------------------------------ alerts and the badge
def test_an_old_database_keeps_its_alerts_and_takes_the_new_kinds(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(SCHEMA_PATH.read_text())
    old.execute(
        "INSERT INTO alerts (business_id, type, severity, title) VALUES (1, 'shortfall', 'high', 'Old one')"
    )
    old.execute("PRAGMA user_version = 2")
    old.commit()
    old.close()

    repo = Repository(path)
    assert repo.schema_version() == len(MIGRATIONS)
    assert [a.title for a in repo.list_alerts(1)] == ["Old one"]
    repo.add_alert(1, None, "watch", "low", 3, {}, "Keep an eye on it", "", [])
    assert repo.open_alert_count(1) == 2


def test_the_badge_counts_open_alerts_until_dismissed(connected_core):
    connected_core.run_daily_check(force=True)
    count = connected_core.open_alert_count()
    assert count >= 1
    connected_core.get_alerts()  # seeing them doesn't change the count
    assert connected_core.open_alert_count() == count
    connected_core.dismiss_alert(connected_core.get_alerts()[0].id)
    assert connected_core.open_alert_count() == count - 1


def test_a_dismissed_alert_is_not_raised_again_by_the_next_check(connected_core):
    connected_core.run_daily_check(force=True)
    before = len(connected_core.get_alerts())
    connected_core.dismiss_alert(connected_core.get_alerts()[0].id)
    summary = connected_core.run_daily_check(force=True)
    assert len(connected_core.get_alerts()) == before - 1
    assert summary.alerts_raised == 0


def test_watch_gets_its_own_low_alert_with_tested_fixes(costume):
    """The costume shop's base case stays above its line, with about a 53% chance of dipping below."""
    [watch] = [a for a in costume.get_alerts() if a.type == "watch"]
    assert watch.severity == "low"
    assert watch.facts["lowest_worst_case"] < watch.facts["low_cash_line"] <= watch.facts["lowest_balance"]
    assert any(a.get("impact") for a in watch.actions)
    assert check_numbers(watch.body, [watch.facts]).passed, watch.body


def test_a_doubled_charge_is_an_alert_and_leaves_the_insights_page():
    cafe = import_business("cafe-la-tertulia", with_one_offs=True)
    [charge] = [a for a in cafe.get_alerts() if a.type == "duplicate_charge"]
    assert charge.facts["payee"] == "Lacteos Del Valle" and charge.title.endswith("charged twice")
    assert charge.actions[0]["label"] == "Ask for a refund"
    assert "duplicate_charge" not in {c["type"] for c in cafe.noticed_cards()}
    assert "duplicate_charge" in {i["type"] for i in cafe.insights()}  # the chat still knows


def test_below_zero_says_payments_could_bounce_and_reads_urgent(bakery):
    [short] = [a for a in bakery.get_alerts() if a.type == "shortfall"]
    assert short.facts["lowest_balance"] < 0
    assert "bounce" in templates.alert_text(short.facts)["body"]
    assert risk_name("act_now", -926) == "urgent"
    assert risk_name("act_now", 900) == "act now"


# ------------------------------------------------------------------ chat
def test_a_new_fridge_is_not_the_new_oven():
    assert best_label("what if i buy a new fridge?", LABELS) is None
    answer = StubClient(TODAY).plan("What if I buy a new fridge?", LABELS)
    assert isinstance(answer, str) and "how much it costs" in answer and "a new fridge" in answer


def test_a_purchase_with_its_price_and_day_is_tested():
    call = StubClient(TODAY).plan("What if I buy a new fridge for $1,200 on Dec 10?", LABELS)
    [adjustment] = call.arguments["adjustments"]
    assert adjustment["type"] == "one_time_expense" and adjustment["amount"] == 1200
    assert adjustment["label"] == "New fridge" and adjustment["date"].endswith("-12-10")


def test_a_purchase_without_a_day_is_asked_about(bakery):
    answer = bakery.ask("What if I buy a new fridge for $1,200?")
    assert answer.scenario is None and "when you'd pay" in answer.text


def test_how_do_i_fix_my_alert_gives_the_tested_fix(bakery):
    answer = bakery.ask("How can I fix my alert?")
    assert "What would help most" in answer.text and "lowest point from" in answer.text


# ------------------------------------------------------------------ questions (live check 2026-11-16)
def test_the_owners_words_beat_the_ais_guess_in_the_list(connected_core):
    """The live site saved "loan repayment (equipment loan)" as Other income: the list still showed
    the AI's guess when Save was pressed."""
    payee = "TRANSF 0045 REF 88213"
    assert connected_core.answer_mystery(payee, "other_income", "loan repayment (equipment loan)") == "loan"
    assert connected_core.answer_mystery(payee, "equipment", "") == "equipment"
    assert connected_core.answer_mystery(payee, "rent", "something my cousin set up") == "rent"


def test_a_guess_must_go_the_same_way_as_the_money():
    assert not fits_direction("other_income", -310)
    assert not fits_direction("rent", 500)
    assert fits_direction("loan", -310) and fits_direction("loan", 5000)
    assert fits_direction("suppliers", -310) and fits_direction("sales", 900)


def test_dismissed_alerts_can_be_seen_and_brought_back(connected_core):
    connected_core.run_daily_check(force=True)
    first = connected_core.get_alerts()[0]
    connected_core.dismiss_alert(first.id)
    assert first.id in [a.id for a in connected_core.dismissed_alerts()]
    connected_core.bring_back_alerts()
    assert connected_core.dismissed_alerts() == []
    assert first.id in [a.id for a in connected_core.get_alerts()]


def test_nothing_coming_up_counts_as_answered(connected_core):
    profile = connected_core.repo.get_profile(connected_core._business().id)
    before = connected_core._questions_answered(profile)[0]
    connected_core.nothing_coming_up()
    profile = connected_core.repo.get_profile(connected_core._business().id)
    assert connected_core._questions_answered(profile)[0] == before + 1
