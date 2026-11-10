"""Demo data generator: Panadería La Esquina (Maria Gómez, Bogotá).

Twelve months of history plus the scheduled items that produce the canonical
demo story (see AHEADLY_APP_SPEC.md section 7). Everything is generated
relative to `today` with a fixed random seed, so the story works on any date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from aheadly.domain import ScheduledItem, Transaction

DEMO_BUSINESS = {
    "name": "Panadería La Esquina",
    "owner_name": "Maria Gómez",
    "city": "Bogotá",
    "low_cash_line": 2000.0,
}
DEMO_OPENING_BALANCE = 8200.0
HISTORY_DAYS = 364

# Weekly pattern of walk-in sales (share of the week per weekday, Mon..Sun).
SALES_WEEKDAY_SHARE = np.array([0.11, 0.11, 0.12, 0.13, 0.17, 0.20, 0.16])
WEEKLY_SALES = 5500.0
WEEKLY_CAFE_PAYMENT = 1500.0
WEEKLY_SUPPLIERS = 3200.0
WEEKLY_OWNER_DRAW = 1300.0
BIWEEKLY_PAYROLL = 3600.0
MONTHLY_RENT = 900.0
# Colombian holidays as (month, day): the bakery closes on these (fixed ones only).
CLOSED_DAYS = {(1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25)}


@dataclass
class DemoDataset:
    transactions: list[Transaction]
    scheduled_items: list[ScheduledItem]
    opening_balance: float = DEMO_OPENING_BALANCE


def _next_weekday(start: date, weekday: int) -> date:
    """First date on/after `start` that falls on `weekday` (0 = Monday)."""
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def build_demo_dataset(today: date | None = None, seed: int = 42) -> DemoDataset:
    today = today or date.today()
    rng = np.random.default_rng(seed)
    start = today - timedelta(days=HISTORY_DAYS)
    next_payroll = _next_payroll_friday(today)
    transactions: list[Transaction] = []

    for offset in range(HISTORY_DAYS):
        day = start + timedelta(days=offset)
        month_index = offset / 30.4
        if (day.month, day.day) not in CLOSED_DAYS:
            sales = WEEKLY_SALES * SALES_WEEKDAY_SHARE[day.weekday()] * rng.normal(1.0, 0.12)
            transactions.append(Transaction(day, round(sales, 2), "Walk-in sales", "sales", "Customers"))
        if day.weekday() == 2:  # Wednesday: a café pays last fortnight's invoice
            transactions.append(
                Transaction(
                    day,
                    round(WEEKLY_CAFE_PAYMENT * rng.normal(1.0, 0.10), 2),
                    "Invoice paid",
                    "cafe_payment",
                    "Café Azul / Café Norte",
                )
            )
        if day.weekday() == 0:  # Monday: flour and dairy
            transactions.append(
                Transaction(
                    day,
                    -round(WEEKLY_SUPPLIERS * rng.normal(1.0, 0.07), 2),
                    "Flour and dairy",
                    "suppliers",
                    "Molinos del Sur",
                )
            )
        if day.weekday() == 4:  # Friday
            transactions.append(Transaction(day, -WEEKLY_OWNER_DRAW, "Owner's draw", "owner_draw", "Maria"))
            transactions.append(
                Transaction(
                    day, -round(60 * rng.normal(1.0, 0.2), 2), "Packaging", "utilities", "Empaques Bogotá"
                )
            )
            if (next_payroll - day).days % 14 == 0:  # same biweekly cadence as the scheduled payroll
                transactions.append(
                    Transaction(day, -BIWEEKLY_PAYROLL, "Payroll (6 staff)", "payroll", "Team")
                )
        if day.day == 15:
            transactions.append(Transaction(day, -MONTHLY_RENT, "Rent", "rent", "Landlord"))
        if day.day == 5:  # utilities trend upward over the year
            transactions.append(
                Transaction(
                    day,
                    -round((220 + 7 * month_index) * rng.normal(1.0, 0.08), 2),
                    "Electricity, gas and water",
                    "utilities",
                    "Enel / Vanti",
                )
            )
        if offset % 45 == 20:
            transactions.append(
                Transaction(
                    day, -round(150 * rng.normal(1.0, 0.3), 2), "Oven maintenance", "maintenance", "Técnico"
                )
            )

    for index, transaction in enumerate(transactions):
        transaction.external_id = f"demo-{index}"

    scheduled = _scheduled_items(today)
    return DemoDataset(transactions=transactions, scheduled_items=scheduled)


def _next_payroll_friday(today: date) -> date:
    """Payroll Fridays fall in weeks 2, 4 and 6 of the horizon (never in the risky week 5)."""
    return _next_weekday(today + timedelta(days=8), 4)


def _scheduled_items(today: date) -> list[ScheduledItem]:
    """Known future money in/out. Dates are relative to today so the story holds."""
    next_payroll = _next_payroll_friday(today)
    cluster_monday = _next_weekday(today + timedelta(days=29), 0)  # week 5
    season_label = "Christmas season" if (today + timedelta(days=42)).month == 12 else "Season peak"
    return [
        ScheduledItem("New oven", -7500, today + timedelta(days=3), kind="planned_purchase"),
        ScheduledItem(
            "Payroll (6 staff)", -BIWEEKLY_PAYROLL, next_payroll, kind="payroll", recurrence="biweekly"
        ),
        ScheduledItem(
            "Rent", -MONTHLY_RENT, _next_day_of_month(today, 15), kind="rent", recurrence="monthly"
        ),
        ScheduledItem("Supplier payment (quarterly flour order)", -4000, cluster_monday, kind="bill"),
        ScheduledItem("Inventory", -1200, cluster_monday + timedelta(days=1), kind="bill"),
        # Two large café orders paid right after the risky week: the seasonal peak of weeks 6 and 7.
        ScheduledItem(
            f"Café Azul {season_label.lower()} order",
            5500,
            cluster_monday + timedelta(days=3),
            kind="receivable",
        ),
        ScheduledItem(
            f"Café Norte {season_label.lower()} order",
            5500,
            cluster_monday + timedelta(days=8),
            kind="receivable",
        ),
    ]


def _next_day_of_month(today: date, day_of_month: int) -> date:
    candidate = today.replace(day=day_of_month)
    if candidate < today:
        candidate = (today.replace(day=1) + timedelta(days=32)).replace(day=day_of_month)
    return candidate


__all__ = ["DemoDataset", "DEMO_BUSINESS", "DEMO_OPENING_BALANCE", "build_demo_dataset"]
