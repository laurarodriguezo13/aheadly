"""Roadmap 4.3: the Insights page's charts, things we noticed with what could help, and the chat tool.

The charts' numbers come from the statement lines (moves between the owner's own accounts and loans
left out); each insight's actions that map to a what-if are tested on the forecast first, like an
alert's (one that changes nothing in the 8 weeks, base case or bad month, stays plain advice).
"""

from datetime import date

import pandas as pd
import pytest

from aheadly.core import insight_charts, pattern_rules
from tests.test_businesses import import_business

TODAY = date(2026, 11, 11)


def _lines(rows: list[tuple]) -> pd.DataFrame:
    """(date, amount, description, category) → the frame the charts read."""
    return pattern_rules.lines_frame([(i, d, a, desc, cat, 0) for i, (d, a, desc, cat) in enumerate(rows, 1)])


SAMPLE = _lines(
    [
        ("2026-07-15", 500.0, "ABONO VENTAS DATAFONO", "sales"),  # July is partial: left out
        ("2026-08-03", 4000.0, "ABONO VENTAS DATAFONO", "sales"),
        ("2026-08-05", -1500.0, "PAGO NOMINA", "payroll"),
        ("2026-08-06", -900.0, "PAGO ARRIENDO", "rent"),
        ("2026-08-07", 2000.0, "DESEMBOLSO CREDITO", "loan"),  # a loan is not money in
        ("2026-09-03", 3000.0, "ABONO VENTAS DATAFONO", "sales"),
        ("2026-09-05", -1500.0, "PAGO NOMINA", "payroll"),
        ("2026-09-06", -900.0, "PAGO ARRIENDO", "rent"),
        ("2026-09-10", -1000.0, "PAGO CREDITO", "loan"),  # nor is repaying it money out
        ("2026-10-03", 3500.0, "TRANSF RECIBIDA CONSTRUCTORA ANDINA", "sales"),
        ("2026-10-05", -1500.0, "PAGO NOMINA", "payroll"),
        ("2026-10-06", -900.0, "PAGO ARRIENDO", "rent"),
        ("2026-10-08", -120.0, "COMPRA PAPELERIA", "other"),
    ]
)


def test_complete_months_leave_out_the_partial_first_and_current_month():
    months = insight_charts.complete_months(SAMPLE, TODAY)
    assert [str(m) for m in months] == ["2026-08", "2026-09", "2026-10"]


def test_money_in_and_out_per_month_without_loans():
    rows = insight_charts.money_in_out(SAMPLE, insight_charts.complete_months(SAMPLE, TODAY))
    assert [(r["money_in"], r["money_out"], r["net"]) for r in rows] == [
        (4000, 2400, 1600),
        (3000, 2400, 600),
        (3500, 2520, 980),
    ]
    facts = insight_charts.money_in_out_facts(rows)
    assert facts["best_month"] == {"month": "Aug 2026", "net": 1600}
    assert facts["months_more_out"] == 0


def test_spending_by_category_adds_up_to_everything_that_went_out():
    names, rows = insight_charts.spending_by_category(SAMPLE, insight_charts.complete_months(SAMPLE, TODAY))
    assert names == ["Payroll", "Rent", "Everything else"]
    assert [sum(r[n] for n in names) for r in rows] == [2400, 2400, 2520]
    facts = insight_charts.spending_facts(names, rows)
    assert facts["biggest"]["category"] == "Payroll" and facts["grew_most"] is None  # 3 months only


def test_taxes_never_count_as_the_cost_that_grew_most():
    names = ["Taxes", "Rent", "Everything else"]
    taxes = [100, 100, 100, 100, 900, 100]  # a lumpy tax payment: up 167%
    rent = [900, 900, 900, 1100, 1100, 1100]  # up 22%
    rows = [
        {"month": m, "Taxes": t, "Rent": r, "Everything else": 100}
        for m, (t, r) in enumerate(zip(taxes, rent))
    ]
    facts = insight_charts.spending_facts(names, rows)
    assert facts["grew_most"] == {"category": "Rent", "monthly_before": 900, "monthly_now": 1100}


def test_income_sources_name_the_customer_and_group_card_sales():
    rows = insight_charts.income_sources(SAMPLE, TODAY)
    assert {r["source"] for r in rows} == {"Card, cash and app sales", "Other money in"}  # one payment only
    assert sum(r["share_pct"] for r in rows) == 100


# ------------------------------------------------------------- the six businesses
@pytest.fixture(scope="module")
def cafe():
    return import_business("cafe-la-tertulia", with_one_offs=True)


@pytest.fixture(scope="module")
def hardware():
    return import_business("ferreteria-don-perno", with_one_offs=True)


def test_cushion_today_matches_the_thin_cushion_insight(cafe):
    thin = next(i for i in cafe.insights() if i["type"] == "thin_cushion")
    rows = cafe.insight_charts()["cushion"]["rows"]
    assert rows[-1]["label"] == "Today"
    assert abs(rows[-1]["weeks"] - thin["facts"]["weeks_covered"]) <= 0.2


def test_biggest_customer_share_matches_the_few_customers_insight(hardware):
    few = next(i for i in hardware.insights() if i["type"] == "few_customers")
    rows = hardware.insight_charts()["income_sources"]["rows"]
    customer = next(r for r in rows if r["source"].startswith("Constructora"))
    assert abs(customer["share_pct"] - few["facts"]["share_pct"]) <= 1


def test_testable_actions_are_tested_first(cafe):
    cards = {c["type"]: c for c in cafe.insight_cards()}
    cancel = cards["new_recurring_charge"]["actions"][0]
    assert cancel["label"] == "Cancel Loggro Pos Sas" and cancel["adjustments"][0]["type"] == "remove_item"
    assert cancel["impact"]["lowest_after"] > cancel["impact"]["lowest_before"]
    pay = cards["owner_pay_high"]["actions"][0]
    assert pay["adjustments"][0]["type"] == "recurring_change" and pay["how_to"]
    refund = cards["duplicate_charge"]["actions"][0]
    assert "adjustments" not in refund and refund["how_to"]  # advice: nothing to test


def test_an_action_counts_when_it_helps_a_bad_month(hardware):
    """The hardware store's pay lands after its lowest day, so the base case doesn't move, but a bad
    month does: the action stays tested and shows that."""
    thin = next(c for c in hardware.insight_cards() if c["type"] == "thin_cushion")
    pay = next(a for a in thin["actions"] if a.get("adjustments"))
    i = pay["impact"]
    assert i["lowest_after"] == i["lowest_before"] and i["worst_after"] > i["worst_before"]
    assert i["chance_after"] < i["chance_before"]


def test_cards_are_worked_out_once_per_forecast_run(cafe):
    assert cafe.insight_cards() is cafe.insight_cards()
    assert cafe.insight_charts() is cafe.insight_charts()


def test_the_chat_says_what_stands_out(cafe):
    answer = cafe.ask("Anything unusual in my numbers?")
    assert "get_insights" in answer.tool_names
    assert "Your cash cushion is thin" in answer.text


def test_nothing_stands_out_for_the_healthy_costume_shop():
    shop = import_business("disfraces-la-fantasia", with_one_offs=True)
    assert shop.insight_cards() == []
    assert "Nothing stands out" in shop.ask("What stands out?").text
