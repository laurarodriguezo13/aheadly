"""Roadmap 4.1: things we noticed. Each rule on small made-up statements: it fires when the pattern
is there, stays quiet when it isn't, and respects what the owner told us (busy and slow months)."""

from datetime import date, timedelta

from aheadly.ai.recurring import Recurring
from aheadly.core import pattern_rules as rules

TODAY = date(2026, 11, 11)


def frame(lines):
    """lines: (date, amount, description, category)."""
    return rules.lines_frame(
        [(i, d.isoformat(), a, desc, cat, 0) for i, (d, a, desc, cat) in enumerate(lines)]
    )


def monthly(amounts_by_month: dict[int, float], description: str, category: str, day: int = 10):
    """One line per month of 2026, e.g. {5: -100, 6: -100, ...}."""
    return [(date(2026, m, day), a, description, category) for m, a in amounts_by_month.items()]


def months(value, first=5, last=10):
    return {m: value for m in range(first, last + 1)}


def kinds(found):
    return [i.type for i in found]


# ------------------------------------------------------------------------------ cushion
def test_thin_cushion_is_less_than_two_weeks_of_spending():
    spending = [(TODAY - timedelta(days=d), -1000.0, "PAGO PROVEEDOR", "suppliers") for d in range(1, 84, 7)]
    assert rules.thin_cushion(frame(spending), TODAY, balance=1500).facts["weeks_covered"] == 1.5
    assert rules.thin_cushion(frame(spending), TODAY, balance=2500) is None


# ------------------------------------------------------------------------------ costs
def test_a_cost_category_creeping_up():
    costs = monthly(
        {5: -1000, 6: -1000, 7: -1000, 8: -1300, 9: -1300, 10: -1300}, "PAGO PSE LACTEOS", "suppliers"
    )
    found = rules.cost_creeping_up(frame(costs), TODAY, seasons=set())
    assert found[0].facts == {
        "category": "suppliers",
        "monthly_before": 1000,
        "monthly_now": 1300,
        "change_pct": 30,
    }


def test_small_or_unknown_or_seasonal_cost_changes_are_not_called_creeping():
    small = monthly({5: -100, 6: -100, 7: -100, 8: -130, 9: -130, 10: -130}, "ENEL", "utilities")  # +$30
    unknown = monthly({5: -1000, 6: -1000, 7: -1000, 8: -1500, 9: -1500, 10: -1500}, "TRANSF 0045", "other")
    assert rules.cost_creeping_up(frame(small + unknown), TODAY, seasons=set()) == []
    stock = monthly(
        {5: -1000, 6: -1000, 7: -1000, 8: -3000, 9: -3000, 10: -3000}, "PAGO PSE DISFRACES", "suppliers"
    )
    assert (
        rules.cost_creeping_up(frame(stock), TODAY, seasons={10}) == []
    )  # October is the owner's busy month


def test_costs_growing_faster_than_sales():
    sales = monthly(months(10000), "ABONO VENTAS DATAFONO", "sales")
    costs = monthly(
        {5: -8000, 6: -8000, 7: -8000, 8: -8800, 9: -8800, 10: -8800}, "PAGO PROVEEDOR", "suppliers"
    )
    found = rules.costs_faster_than_sales(frame(sales + costs), TODAY, seasons=set())
    assert (found.facts["costs_change_pct"], found.facts["sales_change_pct"]) == (10, 0)
    growing = monthly({5: 10000, 6: 10000, 7: 10000, 8: 11000, 9: 11000, 10: 11000}, "ABONO VENTAS", "sales")
    assert rules.costs_faster_than_sales(frame(growing + costs), TODAY, seasons=set()) is None


def test_net_flow_shrinking():
    sales = monthly(months(10000), "ABONO VENTAS DATAFONO", "sales")
    costs = monthly(
        {5: -9500, 6: -9500, 7: -9500, 8: -10500, 9: -10500, 10: -10500}, "PAGO PROVEEDOR", "suppliers"
    )
    found = rules.net_flow_shrinking(frame(sales + costs), TODAY, seasons=set())
    assert found.facts == {"monthly_net_before": 500, "monthly_net_now": -500}
    steady = monthly(months(-9500), "PAGO PROVEEDOR", "suppliers")
    assert rules.net_flow_shrinking(frame(sales + steady), TODAY, seasons=set()) is None


# ------------------------------------------------------------------------------ owner's pay
def test_owner_pay_high_leaves_loans_out():
    sales = monthly(months(10000), "ABONO VENTAS", "sales")
    costs = monthly(months(-8000), "PAGO PROVEEDOR", "suppliers")
    pay = monthly(months(-1800), "TRANSF A CTA AHORROS M GOMEZ", "owner_pay")
    found = rules.owner_pay_high(frame(sales + costs + pay), TODAY)
    assert found.facts == {"monthly_owner_pay": 1800, "monthly_left_before_pay": 2000, "share_pct": 90}
    modest = monthly(months(-1000), "TRANSF A CTA AHORROS M GOMEZ", "owner_pay")
    assert rules.owner_pay_high(frame(sales + costs + modest), TODAY) is None
    # borrowing for stock and repaying it from the season changes nothing
    loan = [
        (date(2026, 8, 1), 5000.0, "DESEMBOLSO CREDITO", "loan"),
        (date(2026, 10, 30), -5200.0, "PAGO CREDITO", "loan"),
    ]
    assert rules.owner_pay_high(frame(sales + costs + modest + loan), TODAY) is None


def test_no_owner_pay_known_means_nothing_to_say():
    assert rules.owner_pay_high(frame(monthly(months(100), "ABONO VENTAS", "sales")), TODAY) is None


# ------------------------------------------------------------------------------ customers
def test_one_customer_bringing_a_quarter_of_the_money():
    card = [(TODAY - timedelta(days=d), 700.0, "ABONO VENTAS DATAFONO", "sales") for d in range(1, 180, 2)]
    big = [
        (TODAY - timedelta(days=d), 12000.0, "TRANSF RECIBIDA CONSTRUCTORA SAS", "sales")
        for d in range(10, 180, 30)
    ]
    found = rules.few_customers(frame(card + big), TODAY)
    assert found.facts["customer"] == "TRANSF RECIBIDA CONSTRUCTORA SAS" and found.facts["share_pct"] >= 25


def test_card_machines_cash_and_platforms_are_not_one_customer():
    takings = [(TODAY - timedelta(days=d), 900.0, "ABONO PASARELA WOMPI", "sales") for d in range(1, 180, 3)]
    clients = [
        (TODAY - timedelta(days=d), 700.0, f"TRANSF RECIBIDA CLIENTE {n}", "sales")
        for n in range(12)
        for d in range(15, 180, 30)
    ]
    assert rules.few_customers(frame(takings + clients), TODAY) is None
    assert rules.is_settlement("CONSIGNACION EFECTIVO") and not rules.is_settlement(
        "TRANSF RECIBIDA HOTEL SIMULADO"
    )


def test_a_customer_paying_later_and_later():
    on_time = [date(2025, 12, 1) + timedelta(days=30 * n) for n in range(6)]
    later = [on_time[-1] + timedelta(days=35 * n) for n in range(1, 5)]
    lines = [(d, 10000.0, "TRANSF RECIBIDA CONSTRUCTORA SAS", "sales") for d in on_time + later]
    found = rules.customers_paying_later(frame(lines))
    assert found[0].facts["days_between_now"] == 35 and found[0].facts["days_between_before"] == 30


def test_a_customer_whose_day_wobbles_is_not_paying_later():
    gaps = [30, 34, 27, 30, 33, 29, 28, 35, 27, 32]
    days = [date(2025, 12, 1)]
    for g in gaps:
        days.append(days[-1] + timedelta(days=g))
    lines = [(d, 700.0, "TRANSF RECIBIDA LIBRERIA SIMULADA", "sales") for d in days]
    assert rules.customers_paying_later(frame(lines)) == []


# ------------------------------------------------------------------------------ charges
def test_the_same_payee_charged_twice_on_one_day():
    lines = [
        (date(2026, 10, 20), -172.23, "PAGO PSE LACTEOS DEL VALLE", "suppliers"),
        (date(2026, 10, 20), -172.23, "PAGO PSE LACTEOS DEL VALLE", "suppliers"),
        (date(2026, 10, 20), -0.69, "GMF 4X1000", "bank_fees"),
        (date(2026, 10, 20), -0.69, "GMF 4X1000", "bank_fees"),
    ]
    found = rules.duplicate_charge(frame(lines), TODAY)
    assert [i.facts for i in found] == [
        {"payee": "PAGO PSE LACTEOS DEL VALLE", "amount": 172.23, "date": "2026-10-20"}
    ]


def test_an_unusual_charge_from_a_payee_never_seen_before():
    usual = [(TODAY - timedelta(days=d), -45.0, "PAGO PSE REPUESTOS", "suppliers") for d in range(1, 300, 3)]
    odd = [(date(2026, 10, 27), -689.30, "COMPRA INTERNACIONAL MKTPLACE*ZX81", "other")]
    found = rules.unusual_charge(frame(usual + odd), TODAY)
    assert [i.facts["payee"] for i in found] == ["COMPRA INTERNACIONAL MKTPLACE*ZX81"]
    small_new = [(date(2026, 10, 27), -60.0, "COMPRA TIENDA NUEVA", "other")]
    assert rules.unusual_charge(frame(usual + small_new), TODAY) == []


def test_a_new_regular_charge():
    pos = Recurring(
        "pago pse loggro pos sas",
        "Pago pse loggro pos sas",
        "out",
        "other",
        "monthly",
        [],
        [],
        -34.9,
        False,
        3,
        date(2026, 10, 18),
    )
    rent = Recurring(
        "pago arriendo",
        "Pago arriendo",
        "out",
        "rent",
        "monthly",
        [],
        [],
        -900.0,
        False,
        12,
        date(2026, 10, 15),
    )
    first = {"pago pse loggro pos sas": date(2026, 8, 18), "pago arriendo": date(2025, 11, 15)}
    found = rules.new_recurring_charge([pos, rent], first, TODAY, history_start=date(2025, 11, 11))
    assert [i.facts["payee"] for i in found] == ["Pago pse loggro pos sas"]
    # with only a few months of statements, everything looks new: say nothing
    assert rules.new_recurring_charge([pos], first, TODAY, history_start=date(2026, 7, 1)) == []


# ------------------------------------------------------------------------------ sales
def test_sales_slowing_by_whole_months():
    falling = monthly({5: 10000, 6: 10000, 7: 10000, 8: 8000, 9: 8000, 10: 8000}, "ABONO VENTAS", "sales")
    assert rules.sales_slowing(frame(falling), TODAY, seasons=set()).facts["change_pct"] == -20
    assert rules.sales_slowing(frame(falling), TODAY, seasons={9}) is None  # September is a slow month
    steady = monthly(months(10000), "ABONO VENTAS", "sales")
    assert rules.sales_slowing(frame(steady), TODAY, seasons=set()) is None


def test_find_puts_the_important_ones_first():
    lines = monthly(months(10000), "ABONO VENTAS", "sales") + monthly(
        months(-9000), "PAGO PROVEEDOR", "suppliers"
    )
    lines += [
        (date(2026, 10, 20), -172.23, "PAGO PSE LACTEOS", "suppliers"),
        (date(2026, 10, 20), -172.23, "PAGO PSE LACTEOS", "suppliers"),
    ]
    found = rules.find(frame(lines), TODAY, balance=1000, seasons=set(), found_recurring=[], first_dates={})
    assert kinds(found) == ["thin_cushion", "duplicate_charge"]
    assert rules.find(frame([]), TODAY, 1000, set(), [], {}) == []


def test_app_core_keeps_the_insights_of_the_latest_run():
    from tests.test_businesses import import_business

    core = import_business("panaderia-la-esquina", with_one_offs=True)
    business = core.status().business
    found = core.insights()
    assert [i["type"] for i in found] == ["owner_pay_high"]
    assert core.repo.list_insights(business.id) == found  # kept in the insights table
    core.run_daily_check(force=True)
    assert core.insights() == found  # a new run works them out again, same statement, same answer
    core.reset()
    assert core.repo.list_insights(business.id) == []
