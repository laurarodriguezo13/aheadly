"""Roadmap 2.7: onboarding questions (detect first, then ask), busy and slow months, and the
connected model's category suggestions for payees the rules couldn't place."""

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from aheadly.ai import seasons
from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import LLMError, LLMReply, ToolCall
from aheadly.ai.models import SeasonalNaiveModel
from tests.test_businesses import KEYS, import_business
from tests.test_example_business import _core


def _months(listed):
    return [int(m[5:7]) for m in listed]


# ------------------------------------------------------------- what gets asked
@pytest.mark.parametrize("slug", sorted(KEYS))
def test_it_asks_about_the_owners_pay_and_the_payees_the_rules_left_out(slug):
    key = KEYS[slug]
    core = import_business(slug)
    questions = core.onboarding()["questions"]
    assert 4 <= len(questions) <= 10 and all(q.why for q in questions)
    assert [q.kind for q in questions][:2] == ["business", "seasons"] and questions[-1].kind == "coming_up"
    owner = [q.payee for q in questions if q.kind == "owner_pay"]
    assert owner == [key["onboarding_answers"]["owner_pay"]["match_hint"]]
    asked = {q.payee for q in questions if q.kind == "mystery"}
    end = date.fromisoformat(key["import"]["statement_end"])
    for payee in key["onboarding_answers"]["mystery_answers"]:
        unplaced = core.repo._conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE description=? AND date>=? AND category='other'",
            (payee, (end - timedelta(days=90)).isoformat()),
        ).fetchone()[0]
        if unplaced:  # what the app already placed (a move from the owner's old account) isn't asked
            assert payee in asked


def test_mystery_questions_say_how_often_and_how_much():
    core = import_business("panaderia-la-esquina")
    mystery = next(q for q in core.onboarding()["questions"] if q.kind == "mystery")
    assert mystery.payee == "TRANSF 0045 REF 88213"
    assert mystery.detail == "About $310 monthly on the 20th, money out."


def test_answers_and_skips_are_remembered_so_the_owner_can_come_back():
    core = import_business("panaderia-la-esquina")
    first = core.onboarding()
    core.answer_business("Bakery", "card every day")
    core.skip_question("seasons")
    core.answer_owner_pay("TRANSF A CTA AHORROS M GOMEZ", True)
    later = core.onboarding()
    assert later["done"] == 3 and later["total"] == first["total"]
    assert [q.kind for q in later["questions"]] == ["mystery", "coming_up"]
    assert core.questions_left() == 2
    profile = core.repo.get_profile(core._business().id)
    assert profile["business_type"] == "Bakery" and "busy_months" not in profile  # skipped: nothing changes
    pay = core.repo._conn.execute(
        "SELECT DISTINCT category FROM transactions WHERE description='TRANSF A CTA AHORROS M GOMEZ'"
    ).fetchall()
    assert [r[0] for r in pay] == ["owner_pay"]


def test_a_mystery_answer_becomes_a_payee_rule():
    core = import_business("panaderia-la-esquina")
    assert core.answer_mystery("TRANSF 0045 REF 88213", words="loan repayment (equipment loan)") == "loan"
    assert core.answer_mystery("COMPRA HOMECENTER", category="equipment") == "equipment"
    asked = [q.payee for q in core.onboarding()["questions"]]
    assert "TRANSF 0045 REF 88213" not in asked
    with pytest.raises(ValueError):
        core.answer_mystery("COMPRA EXITO")


def test_the_example_comes_with_its_owners_answers():
    core = _core()
    core.load_example()
    answers = core.example_answers()
    assert answers["busy_months"] == [12] and answers["slow_months"] == [1]
    assert answers["owner_pay"] == ["TRANSF A CTA AHORROS M GOMEZ"]
    asked = {q.payee for q in core.onboarding()["questions"]}
    assert set(answers["mystery"]) <= asked


# ------------------------------------------------------------- busy and slow months
def test_last_years_busy_month_is_measured_on_money_in():
    core = import_business("panaderia-la-esquina")
    found = core.season_estimates([12], [1])
    assert 0.2 <= found[12] <= 0.4 and -0.2 <= found[1] < 0


def test_a_month_the_statement_disagrees_with_changes_nothing_unless_the_owner_says_so():
    core = import_business("disfraces-la-fantasia")
    # the owner's answer; compared with the other months, last January was busier than normal
    core.set_seasons([10, 2], [11, 12, 1])
    january = next(m for m in core.seasons()["months"] if m["month"] == 1)
    assert january["from_statement"] > 0 and january["used"] == 0.0
    core.set_seasons([10, 2], [11, 12, 1], {1: -0.2})
    assert next(m for m in core.seasons()["months"] if m["month"] == 1)["used"] == -0.2


def test_a_slow_month_lowers_every_case_and_a_busy_month_only_the_best():
    core = import_business("panaderia-la-esquina")
    plain = core.get_dashboard().forecast
    core.set_seasons([12], [])
    busy = core.get_dashboard().forecast
    december = [i for i, p in enumerate(plain.points) if p.date.month == 12]
    last = december[-1]
    best = busy.points[last].balance_p90 - plain.points[last].balance_p90
    base = busy.points[last].balance_p50 - plain.points[last].balance_p50
    assert best > 1000 and 0 <= base < 0.4 * best  # the base case counts on little of it
    core.set_seasons([], [12], {12: -0.3})  # the owner's own estimate (the statement says busy)
    slow = core.get_dashboard().forecast
    assert slow.points[last].balance_p10 < plain.points[last].balance_p10 - 500
    assert slow.points[last].balance_p50 < plain.points[last].balance_p50 - 500


def test_no_answer_no_seasonal_change():
    core = import_business("panaderia-la-esquina")
    assert core._month_shift(core._business().id) == {}


def test_months_outside_the_statement_wait_for_the_owners_estimate():
    days = pd.date_range("2026-03-01", "2026-10-31", freq="D")
    money_in = seasons.daily_money_in(pd.DataFrame({"date": days, "money_in": 100.0}))
    assert seasons.month_estimates(money_in, [12], []) == {12: None}


def test_a_busy_shift_in_the_engine_spreads_between_none_and_all():
    engine = ForecastEngine(SeasonalNaiveModel(), n_paths=400)
    dates = pd.date_range("2026-10-01", periods=60, freq="D")
    history = pd.DataFrame({"date": dates, "net_flow": 0.0})
    result = engine.forecast(history, 0, [], date(2026, 12, 1), 31, month_shift={12: 100.0})
    end = result.points[-1]
    assert end.balance_p50 == pytest.approx(0, abs=50)
    assert 2000 < end.balance_p90 <= 3100


# ------------------------------------------------------------- the model's suggestions
class _FakeModel:
    name = "fake"

    def __init__(self, suggestions=None, fail=False):
        self.suggestions, self.fail, self.seen = suggestions or [], fail, []

    def chat(self, messages, tools=None):
        self.seen.append(json.dumps(messages, ensure_ascii=False))
        if self.fail:
            raise LLMError("quota")
        return LLMReply(tool_calls=[ToolCall("1", "suggest_categories", {"suggestions": self.suggestions})])


def _with(model):
    core = import_business("taller-los-pistones")
    core.translator._llm = model
    return core


def test_the_model_sees_payee_names_only_and_its_guess_is_prefilled():
    model = _FakeModel(
        [
            {"payee": "TRANSF 0078 REF 55120", "category": "loan", "reason": "Fixed monthly transfer"},
            {"payee": "COMPRA INTERNACIONAL MKTPLACE*ZX81", "category": "spaceships", "reason": "?"},
            {"payee": "SOMEONE NOT ASKED", "category": "rent", "reason": "?"},
        ]
    )
    core = _with(model)
    questions = {q.payee: q for q in core.onboarding()["questions"] if q.kind == "mystery"}
    assert questions["TRANSF 0078 REF 55120"].suggestion == "loan"
    assert questions["COMPRA INTERNACIONAL MKTPLACE*ZX81"].suggestion is None  # not a category: dropped
    sent = " ".join(model.seen)
    assert "TRANSF 0078 REF 55120" in sent and "285" not in sent and "689" not in sent  # no amounts
    # nothing changes until the owner confirms
    category = core.repo._conn.execute(
        "SELECT DISTINCT category FROM transactions WHERE description='TRANSF 0078 REF 55120'"
    ).fetchone()[0]
    assert category == "other"


def test_suggestions_are_asked_for_once():
    model = _FakeModel([{"payee": "TRANSF 0078 REF 55120", "category": "loan", "reason": "x"}])
    core = _with(model)
    core.onboarding()
    core.onboarding()
    assert len(model.seen) == 1


def test_a_failed_model_still_asks_the_questions():
    core = _with(_FakeModel(fail=True))
    mysteries = [q for q in core.onboarding()["questions"] if q.kind == "mystery"]
    assert mysteries and all(q.suggestion is None for q in mysteries)
