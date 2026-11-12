"""Roadmap 2.3: recurring payments and income found in the statement, on their real dates."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from aheadly.ai.forecast_engine import expand_scheduled_items
from aheadly.ai.recurring import TxLine, detect, drop_duplicates, month_rule_dates
from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.domain import ScheduledItem

TODAY = date(2026, 11, 11)
START = date(2025, 11, 11)


def _days(first: date, step: int, until: date = date(2026, 11, 10)) -> list[date]:
    out, d = [], first
    while d <= until:
        out.append(d)
        d += timedelta(days=step)
    return out


def _monthly(day: int, shift: str = "next") -> list[date]:
    out = []
    for i in range(12):
        y, m = divmod(2025 * 12 + 10 + i, 12)
        d = date(y, m + 1, day)
        while d.weekday() >= 5:
            d += timedelta(days=1 if shift == "next" else -1)
        if START <= d <= date(2026, 11, 10):
            out.append(d)
    return out


def _lines(description: str, dates: list[date], amount, category: str = "other") -> list[TxLine]:
    amounts = amount if isinstance(amount, list) else [amount] * len(dates)
    return [
        TxLine(1000 + i, d, a, description, category, False) for i, (d, a) in enumerate(zip(dates, amounts))
    ]


def _found(lines: list[TxLine]):
    found = detect(lines, TODAY)
    assert len(found) == 1, found
    return found[0]


# ------------------------------------------------------------- finding the rule
def test_weekly_payroll_on_fridays():
    r = _found(_lines("PAGO NOMINA", _days(date(2025, 11, 14), 7), -1331.2, "payroll"))
    assert (r.cadence, r.amount, r.amount_varies, r.next_dates) == (
        "weekly",
        -1331.2,
        False,
        [date(2026, 11, 13)],
    )
    assert r.scheduled


def test_rent_on_the_15th_moves_off_weekends():
    r = _found(_lines("PAGO ARRIENDO LOCAL", _monthly(15), -900.0, "rent"))
    assert r.cadence == "monthly" and r.rules == ["month_day:15:next:1"]
    # Nov 15, 2026 is a Sunday: the payment falls on Monday the 16th
    assert month_rule_dates(r.rules[0], r.next_dates[0], date(2026, 12, 31)) == [
        date(2026, 11, 16),
        date(2026, 12, 15),
    ]


def test_payroll_twice_a_month_on_the_15th_and_last_business_day():
    dates = sorted(_monthly(15, "prev") + [_last_bd(y, m) for y, m in _months()])
    r = _found(_lines("PAGO NOMINA", dates, -1380.0, "payroll"))
    assert r.cadence == "twice a month"
    assert sorted(r.rules) == ["month_day:15:prev:1", "month_day:last_bd:prev:1"]


def test_a_quarterly_order_and_a_december_bonus():
    flour = _found(
        _lines(
            "PAGO PSE HARINERA",
            [date(2025, 12, 15), date(2026, 3, 16), date(2026, 6, 15), date(2026, 9, 15)],
            -4000.0,
            "suppliers",
        )
    )
    assert (flour.cadence, flour.next_dates) == ("quarterly", [date(2026, 12, 15)])
    bonus = _found(_lines("PAGO NOMINA PRIMA", [date(2025, 12, 19), date(2026, 6, 26)], -2884.27, "payroll"))
    assert (bonus.cadence, bonus.certainty) == ("twice a year", "maybe")
    # last year it came on Friday Dec 19; this year the 19th is a Saturday: staff are paid on Friday
    assert month_rule_dates(bonus.rules[0], bonus.next_dates[0], date(2026, 12, 31)) == [date(2026, 12, 18)]


def test_daily_card_sales_stay_with_the_model():
    dates = [d for d in _days(date(2026, 5, 1), 1) if d.weekday() < 6]
    amounts = [400 + (i * 37) % 160 for i in range(len(dates))]
    r = _found(_lines("ABONO VENTAS DATAFONO", dates, amounts, "sales"))
    assert (r.cadence, r.amount_varies, r.scheduled) == ("daily", True, False)


def test_a_payment_that_drifts_later_each_month_goes_by_the_gap():
    dates = [date(2026, 3, 4), date(2026, 3, 30), date(2026, 5, 4), date(2026, 6, 1), date(2026, 7, 6),
             date(2026, 8, 10), date(2026, 9, 14), date(2026, 10, 20)]  # fmt: skip
    r = _found(_lines("TRANSF RECIBIDA CONSTRUCTORA", dates, 10000.0, "sales"))
    assert r.cadence == "monthly" and r.rules[0].startswith("every:")
    assert date(2026, 11, 20) <= r.next_dates[0] <= date(2026, 11, 28)


def test_a_reference_number_that_changes_is_still_one_payee():
    dates = _days(date(2026, 6, 2), 7)
    lines = [
        TxLine(i, d, 300.0, f"TRANSF NEQUI REF {50000 + i * 7}", "sales", False) for i, d in enumerate(dates)
    ]
    assert _found(lines).match_key == "transf nequi ref #"


def test_a_fixed_reference_keeps_its_number():
    r = _found(_lines("TRANSF 0045 REF 88213", _monthly(20), -310.0, "loan"))
    assert r.match_key == "transf 0045 ref 88213"


def test_stopped_payments_and_one_offs_are_not_recurring():
    old_account = _lines("TRANSF INTERBANCARIA", _monthly(5)[:8], 500.0)  # stops in July
    assert detect(old_account, TODAY) == []
    assert detect(_lines("COMPRA ALKOSTO", [date(2026, 4, 2)], -640.0), TODAY) == []


def test_seasonal_staff_are_not_forecast_all_year():
    dates = [date(2025, 11, 14), date(2025, 11, 28), date(2026, 10, 15), date(2026, 10, 30)]
    found = detect(_lines("PAGO NOMINA TEMPORADA", dates, -600.0, "payroll"), TODAY)
    assert all(not r.scheduled for r in found)


def test_moves_between_own_accounts_are_found_but_not_forecast():
    lines = [
        TxLine(i, d, -1000.0, "TRANSF A CTA CORRIENTE", "transfer_internal", True)
        for i, d in enumerate(_monthly(3))
    ]
    r = _found(lines)
    assert r.internal and not r.scheduled


def test_flags_a_missed_payment_and_a_changed_amount():
    r = _found(_lines("PAGO CLARO", _monthly(3), -41.9, "utilities"))  # due Nov 3; not there by the 11th
    assert r.missed
    r = _found(_lines("PAGO NOMINA", _days(date(2025, 11, 14), 7), [-1300.0] * 50 + [-1331.2] * 3, "payroll"))
    assert r.amount_changed is False and r.amount == -1331.2  # three in a row: the new amount


# ------------------------------------------------------------- counted once
def test_a_known_payment_replaces_the_detected_one():
    events = [
        (date(2026, 12, 15), -4000.0, "Pago pse harinera", True),
        (date(2026, 12, 15), -900.0, "Pago arriendo", True),
        (date(2026, 12, 15), -4000.0, "Quarterly flour order", False),
        (date(2026, 12, 16), 5500.0, "Christmas order", False),
        (date(2026, 12, 14), 352.58, "Café weekly", True),
    ]
    kept = drop_duplicates(events)
    labels = [label for _, _, label in kept]
    assert "Pago pse harinera" not in labels
    assert {"Quarterly flour order", "Pago arriendo", "Christmas order", "Café weekly"} == set(labels)


def test_month_rules_in_the_forecast():
    rent = ScheduledItem("Rent", -900.0, date(2026, 11, 15), recurrence="month_day:15:next:1")
    events = expand_scheduled_items([rent], TODAY, date(2027, 1, 31))
    assert [d for d, _, _ in events] == [date(2026, 11, 16), date(2026, 12, 15), date(2027, 1, 15)]
    moved = ScheduledItem("Rent", -900.0, date(2026, 11, 30), recurrence="month_day:15:next:1")
    assert [d for d, _, _ in expand_scheduled_items([moved], TODAY, date(2026, 12, 31))] == [
        date(2026, 11, 30),
        date(2026, 12, 15),
    ]
    customer = ScheduledItem("Big customer", 10000.0, date(2026, 11, 24), recurrence="every:35")
    assert [d for d, _, _ in expand_scheduled_items([customer], TODAY, date(2027, 1, 5))] == [
        date(2026, 11, 24),
        date(2026, 12, 29),
    ]


# ------------------------------------------------------------- through App Core
PROFILE = {"name": "Test", "owner_name": "", "city": ""}


def _statement() -> str:
    rows = []
    for d in _days(date(2026, 5, 1), 1):
        if d.weekday() < 6:
            rows.append((d, "ABONO VENTAS DATAFONO", 450 + (d.toordinal() * 37) % 120))
        if d.weekday() == 4:
            rows.append((d, "PAGO NOMINA", -1300))
        if d.day == 15:
            rows.append((d, "PAGO ARRIENDO LOCAL", -900))
    rows.sort()
    balance, out = 20000.0, ["Date,Description,Amount,Balance"]
    for d, desc, amount in rows:
        balance += amount
        out.append(f"{d.isoformat()},{desc},{amount},{balance:.2f}")
    return "\n".join(out) + "\n"


@pytest.fixture
def uploaded(core):
    core._today = TODAY
    core.connect(CsvConnector(_statement(), None, "cuenta.csv", business_profile=PROFILE))
    return core


def test_upload_schedules_recurring_items_and_links_their_lines(uploaded):
    items = {i.label: i for i in uploaded.repo.list_scheduled_items(uploaded.status().business.id)}
    assert items["Pago nomina"].recurrence == "weekly" and items["Pago nomina"].status == "detected"
    assert items["Pago arriendo local"].recurrence.startswith("month_day:15")
    linked = uploaded.repo._conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE scheduled_item_id IS NOT NULL"
    ).fetchone()[0]
    payroll_and_rent = uploaded.repo._conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE description IN ('PAGO NOMINA', 'PAGO ARRIENDO LOCAL')"
    ).fetchone()[0]
    assert linked == payroll_and_rent
    assert uploaded.planned_items() == []  # Accounts lists only what the owner told us


def test_rent_is_a_dip_on_its_day_and_nothing_is_counted_twice(uploaded):
    forecast = uploaded.get_dashboard().forecast
    flows = {p.date: p.net_flow_p50 for p in forecast.points}
    assert flows[date(2026, 11, 16)] < flows[date(2026, 11, 17)] - 800  # Sunday the 15th → Monday
    history = uploaded._model_history(uploaded.status().business)
    assert history["net_flow"].min() >= 0  # only card sales are left for the model (0 on Sundays)


def test_removing_a_found_payment_in_a_plan_survives_a_new_upload(uploaded):
    result = uploaded.run_what_if([{"type": "remove_item", "label": "Pago arriendo"}], "No rent")
    uploaded.save_plan(result)
    uploaded.connect(CsvConnector(_statement(), None, "cuenta.csv", business_profile=PROFILE))
    labels = [i.label for i in uploaded.repo.list_scheduled_items(uploaded.status().business.id)]
    assert "Pago arriendo local" not in labels
    history = uploaded._model_history(uploaded.status().business)
    assert history["net_flow"].min() >= 0  # and its past lines don't come back into the history


def test_next_big_payment_is_big_not_just_next():
    from .test_example_business import _core

    core = _core()
    core.load_example()
    due, amount, label = core.get_dashboard().next_payment
    assert (label, amount) == ("New oven", -7500.0)


def test_detected_recurring_lists_everything(uploaded):
    found = {r.label: r for r in uploaded.detected_recurring()}
    assert found["Abono ventas datafono"].cadence == "daily"
    assert not found["Abono ventas datafono"].scheduled


# ------------------------------------------------------------- helpers
def _months():
    for i in range(12):
        y, m = divmod(2025 * 12 + 10 + i, 12)
        yield y, m + 1


def _last_bd(y: int, m: int) -> date:
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
