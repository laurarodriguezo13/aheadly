"""Roadmap R.2: the loan what-if on the Financing sub-tab, and the four sidebar groups."""

from datetime import date

import pytest

from aheadly.core.financing import add_months, loan_payments, monthly_payment
from aheadly.ai.scenarios import apply_adjustments, parse_adjustment


def test_monthly_payment_pays_the_loan_off():
    assert monthly_payment(12000, 0, 12) == 1000
    assert monthly_payment(10000, 12, 12) == pytest.approx(888.49, abs=0.01)  # 1% a month
    payments = loan_payments(10000, 12, 12, date(2026, 11, 11))
    assert len(payments) == 12 and payments[0][0] == date(2026, 12, 11)
    assert sum(p for _, p in payments) == pytest.approx(10661.85, abs=0.05)


def test_a_month_later_on_short_months():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2027, 12, 15), 1) == date(2028, 1, 15)


def test_the_loan_adjustment_adds_the_money_the_fees_and_the_payments():
    adjustment = parse_adjustment(
        {
            "type": "loan",
            "amount": 6000,
            "yearly_rate": 0,
            "months": 3,
            "fees": 50,
            "start_date": "2026-11-12",
        }
    )
    lines = apply_adjustments([], [adjustment], date(2026, 11, 11))
    assert [(line.label, line.amount) for line in lines] == [
        ("Loan", 6000),
        ("Loan fees", -50),
        ("Loan payment", -2000),
        ("Loan payment", -2000),
        ("Loan payment", -2000),
    ]


@pytest.mark.parametrize(
    "bad",
    [{"amount": 0}, {"months": 0}, {"months": 200}, {"yearly_rate": -1}, {"fees": -5}],
)
def test_a_loan_needs_sensible_numbers(bad):
    raw = {
        "type": "loan",
        "amount": 6000,
        "yearly_rate": 10,
        "months": 6,
        "fees": 0,
        "start_date": "2026-11-12",
    }
    with pytest.raises(ValueError):
        parse_adjustment({**raw, **bad})


def test_testing_a_loan_on_the_bakery(connected_core):
    core = connected_core
    loan = core.test_loan(5000, 18, 6, fees=100)
    assert loan["monthly_payment"] == pytest.approx(877.63, abs=0.01)
    assert loan["payments"] == 6 and loan["payments_in_window"] == 1
    assert loan["total_cost"] == pytest.approx(loan["interest"] + 100)
    assert loan["lowest_after"] > loan["lowest_before"]  # $5,000 now, one payment in the 8 weeks
    assert core.saved_scenarios() == [] or all(
        s["name"] != loan["result"].name for s in core.saved_scenarios()
    )
    with pytest.raises(ValueError):
        core.test_loan(5000, 18, 6, start=date(2000, 1, 1))


def _bootstrap_names() -> tuple[set[str], dict[str, tuple]]:
    """PAGES and GROUPS from aheadly/ui/bootstrap.py, read without importing Streamlit."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("aheadly/ui/bootstrap.py").read_text())
    pages, groups = set(), {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "PAGES":
            pages = {e.value for e in node.value.generators[0].iter.elts}
        if isinstance(node, ast.Assign) and node.targets[0].id == "GROUPS":
            groups = ast.literal_eval(node.value)
    return pages, groups


def test_every_page_is_in_exactly_one_group_and_has_a_name():
    from aheadly.ui import copy

    pages, groups = _bootstrap_names()
    in_groups = [page for members in groups.values() for page in members]
    assert sorted(in_groups) == sorted(pages)
    assert set(groups) == set(copy.NAV_GROUPS) and set(copy.NAV) == pages
    for use_case in ("Early-warning alerts", "Ask about my numbers", "Test a what-if", "Connect accounts"):
        assert use_case in copy.NAV.values()  # the four use cases stay visible as sub-tab names


def test_the_question_count_is_there_before_the_first_answer():
    """Issue 17: the sidebar showed the count only after the Questions page had been opened."""
    from tests.test_businesses import import_business

    core = import_business("panaderia-la-esquina")
    assert core.repo.get_profile(core._business().id).get("questions_left") is None
    assert core.questions_left() == len(core.onboarding()["questions"]) > 0
