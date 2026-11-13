"""Roadmap 3.5: one-click stress tests.

Four bad surprises, built from the business's own numbers: sales 20% lower for 4 weeks, the biggest
money coming in arriving a month late, the main supplier 10% dearer, and a surprise bill the size
of a month's rent (or a week of spending without rent). Each one says "you'd be fine" or "you'd need
about $X" to stay above the line, and what would help.
"""

from datetime import timedelta

from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
from aheadly.domain import ScheduledItem
from tests.conftest import TODAY
from tests.test_businesses import import_business


def test_four_surprises_from_the_business_own_numbers():
    core = import_business("estudio-lapiz-rojo", with_one_offs=True)
    tests = core.stress_tests()
    order = ["sales_drop", "late_customer", "supplier_up", "surprise_bill"]
    keys = [t["key"] for t in tests]
    assert keys == [k for k in order if k in keys]  # a surprise the numbers can't build is left out
    assert len(tests) >= 3
    for t in tests:
        assert t["label"] and t["detail"] and t["adjustments"] and t["verdict"] in ("fine", "short")


def test_verdict_and_gap_follow_the_base_case():
    core = import_business("panaderia-la-esquina", with_one_offs=True)  # already tight
    line = core.status().business.low_cash_line
    for t in core.stress_tests():
        lowest = t["impact"]["lowest_after"]
        if t["verdict"] == "short":
            assert t["gap"] == round(line - lowest) and t["gap"] > 0
        else:
            assert lowest >= line and t["gap"] is None


def test_a_healthy_business_is_fine_with_most_surprises():
    tests = import_business("estudio-lapiz-rojo", with_one_offs=True).stress_tests()
    assert sum(t["verdict"] == "fine" for t in tests) >= len(tests) - 1


def test_short_surprises_come_with_what_would_help():
    tests = import_business("panaderia-la-esquina", with_one_offs=True).stress_tests()
    short = [t for t in tests if t["verdict"] == "short"]
    assert short and any(t["fixes"] for t in short)
    for t in short:
        for fix in t["fixes"]:
            assert fix["impact"]["lowest_after"] >= fix["impact"]["lowest_before"]


def test_sales_drop_lasts_four_weeks_only():
    items = apply_adjustments(
        [],
        [
            parse_adjustment(
                {"type": "revenue_change", "percent": -20, "start_date": TODAY.isoformat(), "weeks": 4}
            )
        ],
        TODAY,
        weekly_sales=1000,
    )
    from aheadly.ai.forecast_engine import expand_scheduled_items

    events = expand_scheduled_items(items, TODAY, TODAY + timedelta(days=55))
    assert len(events) == 4 and all(amount == -200 for _, amount, _ in events)


def test_stress_tests_are_not_kept_in_the_owners_history():
    core = import_business("estudio-lapiz-rojo", with_one_offs=True)
    core.stress_tests()
    assert core.saved_scenarios() == []


def test_without_rent_the_surprise_is_a_week_of_spending(connected_core):
    business = connected_core.status().business
    for item in connected_core.repo.list_scheduled_items(business.id):
        assert isinstance(item, ScheduledItem)
    bill = next(t for t in connected_core.stress_tests() if t["key"] == "surprise_bill")
    assert bill["adjustments"][0]["type"] == "one_time_expense" and bill["adjustments"][0]["amount"] > 0


def test_a_what_if_bill_never_cancels_a_real_payment():
    """Found while building 3.5: a surprise bill the size of the rent, a week before the rent, was
    taken for the rent itself and the rent dropped out, so the "bad" scenario looked better. A
    what-if's own lines are never "the same money" as a payment found in the statement."""
    core = import_business("ferreteria-don-perno", with_one_offs=True)
    rent = next(i for i in core.repo.list_scheduled_items(core.status().business.id) if i.category == "rent")
    from aheadly.ai.forecast_engine import expand_scheduled_items

    due = expand_scheduled_items([rent], core.today, core.today + timedelta(days=55))[0][0]
    bill = {"type": "one_time_expense", "amount": -rent.amount, "date": (due - timedelta(days=3)).isoformat()}
    result = core.run_what_if([bill])
    assert result.scenario.points[-1].balance_p50 < result.baseline.points[-1].balance_p50 + rent.amount / 2


def test_a_stress_chart_is_not_saved_as_a_what_if():
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    before = len(core.saved_scenarios())
    test = core.stress_tests()[0]
    result = core.stress_result(test["key"])
    assert round(result.scenario.lowest.balance_p50) == test["impact"]["lowest_after"]
    assert len(core.saved_scenarios()) == before


def test_the_supplier_surprise_hits_a_payment_the_forecast_counts():
    """The bakery's biggest supplier payment in the statement (the quarterly flour) is replaced in the
    forecast by the owner's own "Quarterly flour order", so raising it changed nothing (found in the
    review after Phase 3). The surprise must pick a supplier payment that actually counts."""
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    test = next(t for t in core.stress_tests() if t["key"] == "supplier_up")
    assert test["impact"]["lowest_after"] < test["impact"]["lowest_before"]
