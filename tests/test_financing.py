"""Roadmap 3.6: the financing helper.

First it says whether a gap is about timing (money is coming, just late) or structural (more goes out
than comes in: borrowing only delays the problem). For a timing gap it compares only the options the
owner says they have, by their cost in dollars, each tested as a what-if with its repayment, so paying
it back can't open a new gap. Nothing is offered, no lender named, not financial advice.
"""

from datetime import date, timedelta

import pytest

from aheadly.ai.guardrails import check_numbers
from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
from aheadly.core import financing
from aheadly.domain import ForecastPoint, ForecastResult
from tests.conftest import TODAY
from tests.test_businesses import import_business

LINE = 1000.0


def _forecast(base: list[float], worst: list[float] | None = None) -> ForecastResult:
    worst = worst or [b - 500 for b in base]
    points = [
        ForecastPoint(TODAY + timedelta(days=i + 1), w, b, b + 500, 0.0)
        for i, (b, w) in enumerate(zip(base, worst))
    ]
    return ForecastResult(base[0], points, "test")


def test_gap_dates_and_size():
    f = _forecast([3000, 2000, 400, 600, 1500, 2500, 2600])
    g = financing.gap(f, LINE)
    assert g["base"] == 600 and g["base_dips"]
    assert g["start"] == TODAY + timedelta(days=3)  # first day below the line
    assert g["low_date"] == TODAY + timedelta(days=3)
    assert g["recovery"] == TODAY + timedelta(days=5)  # back above for good
    assert financing.amount_needed(g) == 600


def test_verdicts():
    timing = financing.gap(_forecast([3000, 400, 2500]), LINE)
    no_recovery = financing.gap(_forecast([3000, 2000, 400]), LINE)
    fine = financing.gap(_forecast([5000, 5000, 5000]), LINE)
    assert financing.verdict(timing, regular=150) == "timing"
    assert financing.verdict(timing, regular=-80) == "structural"  # normal weeks lose money
    assert financing.verdict(no_recovery, regular=150) == "structural"  # never gets back above it
    assert financing.verdict(fine, regular=-80) == "none"  # even a bad month stays above the line


def test_cost_is_interest_for_the_days_plus_fees():
    assert financing.cost(3000, 24, 30) == pytest.approx(3000 * 0.24 * 30 / 365, abs=0.01)
    assert financing.cost(3000, 24, 30, fee=20) == pytest.approx(59.18 + 20, abs=0.01)
    # a 2% fee for 30 days is about 24% a year
    assert financing.yearly_rate(1000, 20, 30) == pytest.approx(24.3, abs=0.1)


def test_repayment_never_opens_a_new_gap():
    f = _forecast([3000, 400, 1100, 1300, 2500, 2600, 2700])
    low = TODAY + timedelta(days=2)
    # with a $350 cost, repaying on day 3 or 4 would leave $750 / $950 below the line: day 5 is the first safe day
    assert financing.repay_date(f, LINE, low, cost=350) == TODAY + timedelta(days=5)
    assert financing.repay_date(f, LINE, low, cost=250) == TODAY + timedelta(days=4)
    assert financing.repay_date(f, LINE, low, cost=5000) is None


def test_options_are_checked():
    with pytest.raises(ValueError, match="rate"):
        financing.check_option({"kind": "credit_line", "limit": 5000})
    with pytest.raises(ValueError, match="how much"):
        financing.check_option({"kind": "card", "rate": 30})
    with pytest.raises(ValueError, match="payment"):
        financing.check_option({"kind": "supplier_terms", "extra_days": 30})
    option = financing.check_option(
        {"kind": "loan", "limit": "4000", "rate": "18", "fee": "", "arrive_days": 5}
    )
    assert option == {"kind": "loan", "limit": 4000.0, "rate": 18.0, "fee": 0.0, "arrive_days": 5.0}


def test_financing_adjustment_brings_money_in_and_pays_it_back():
    adj = parse_adjustment(
        {
            "type": "financing",
            "amount": 3000,
            "start_date": "2026-12-10",
            "repay_date": "2026-12-16",
            "cost": 15,
            "label": "Business credit card",
        }
    )
    items = apply_adjustments([], [adj], TODAY)
    assert [(i.amount, i.due_date) for i in items] == [
        (3000.0, date(2026, 12, 10)),
        (-3015.0, date(2026, 12, 16)),
    ]
    with pytest.raises(ValueError):
        parse_adjustment({"type": "financing", "amount": 3000, "start_date": "2026-12-10"})
    with pytest.raises(ValueError):
        apply_adjustments(
            [],
            [
                parse_adjustment(
                    {"type": "financing", "amount": 1, "start_date": "2026-12-10", "repay_date": "2026-12-01"}
                )
            ],
            TODAY,
        )


@pytest.fixture(scope="module")
def bakery():
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    for option in (
        {"kind": "credit_line", "limit": 5000, "rate": 24, "fee": 20},
        {"kind": "card", "limit": 3000, "rate": 30},
        {"kind": "own_money", "limit": 2000},
        {"kind": "loan", "limit": 5000, "rate": 20, "arrive_days": 60},
    ):
        core.add_financing_option(option)
    return core


def test_bakery_timing_gap_compares_its_own_options(bakery):
    result = bakery.compare_financing()
    line = result["low_cash_line"]
    assert result["verdict"] == "timing"
    assert result["need"] >= result["gap"]["base"] > 0
    usable = [p for p in result["options"] if p["feasible"] and p["impact"]["covers"]]
    assert [p["kind"] for p in usable] == ["card", "credit_line"]  # cheapest first
    for p in usable:
        assert p["impact"]["lowest_after"] >= line  # repayment included: no new gap anywhere
        assert p["repay"] > p["take"]
    reasons = {p["kind"]: p["reason"] for p in result["options"]}
    assert reasons["own_money"] == "limit" and reasons["loan"] == "late"
    assert [a["kind"] for a in result["actions"]] == ["financing", "financing"]
    assert result["actions"][0]["label"].startswith("Use your business credit card")


def test_a_structural_gap_gets_no_options():
    core = import_business("cafe-la-tertulia", with_one_offs=True)
    core.add_financing_option({"kind": "credit_line", "limit": 9000, "rate": 20})
    result = core.compare_financing()
    assert result["verdict"] == "structural"
    assert result["normal_week"] < 0
    assert result["options"] == [] and result["actions"] == []


def test_options_are_kept_and_removed(bakery):
    before = len(bakery.financing_options())
    bakery.add_financing_option({"kind": "own_money", "limit": 500})
    assert len(bakery.financing_options()) == before + 1
    bakery.remove_financing_option(before)
    assert len(bakery.financing_options()) == before


def test_moving_the_owners_payment_moves_the_money():
    """The owner's "Quarterly flour order" stands in for the flour payment found in the statement;
    moving it a month must not bring the statement's copy back (it did before 3.6)."""
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    before = core._scenario([{"type": "one_time_expense", "amount": 1, "label": "x"}])
    moved = core._scenario(
        [{"type": "move_item", "label": "Quarterly flour order", "new_date": "2027-01-14"}]
    )
    assert moved.scenario.lowest.balance_p50 > before.scenario.lowest.balance_p50 + 2000


def test_a_credit_line_in_the_statement_is_pointed_out():
    core = import_business("disfraces-la-fantasia", with_one_offs=True)
    assert core.financing_hint() == {"times": 9, "biggest": 9000}
    assert import_business("estudio-lapiz-rojo", with_one_offs=True).financing_hint() is None


def test_chat_compares_financing_with_numbers_from_code(bakery):
    answer = bakery.ask("How can I cover this?")
    assert answer.tool_names == ["compare_financing"]
    assert "timing gap" in answer.text and "financial advice" in answer.text
    assert check_numbers(answer.text, [bakery.financing_summary()]).passed


def test_a_financing_action_can_be_saved_as_the_plan():
    """Save as my plan kept failing on the database's list of kinds (found in the review)."""
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    core.add_financing_option({"kind": "card", "limit": 5000, "rate": 30})
    action = core.compare_financing()["actions"][0]
    core.save_plan(core.run_what_if(action["adjustments"], action["label"]))
    assert core.get_dashboard().forecast.lowest.balance_p50 >= core.status().business.low_cash_line
    assert not [a for a in core.get_alerts() if a.type == "shortfall" and a.severity == "high"]


def test_saving_a_moved_payment_keeps_what_was_tested():
    """The owner's "Quarterly flour order" stands in for the flour payment found in the statement.
    Tested a month later it lifts the lowest balance; saved as the plan, the forecast must show the
    same, not bring the statement's copy back (found in the review after Phase 3)."""
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    result = core.run_what_if(
        [{"type": "move_item", "label": "Quarterly flour order", "new_date": "2027-01-14"}], "Flour later"
    )
    core.save_plan(result)
    saved = core.get_dashboard().forecast.lowest.balance_p50
    assert saved == pytest.approx(result.scenario.lowest.balance_p50, abs=150)


def test_moving_it_on_how_we_built_it_also_moves_the_money():
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    before = core.get_dashboard().forecast.lowest.balance_p50
    flour = next(
        i
        for i in core.repo.list_scheduled_items(core.status().business.id)
        if i.label == "Quarterly flour order"
    )
    core.update_plan_item(flour.id, due_date=date(2027, 1, 14))
    assert core.get_dashboard().forecast.lowest.balance_p50 > before + 2000
