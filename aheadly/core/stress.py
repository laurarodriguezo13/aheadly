"""One-click stress tests (roadmap 3.5): four bad surprises built from the business's own numbers.

- sales_drop: sales 20% lower for 4 weeks (from the business's real weekly sales).
- late_customer: the biggest money coming in (one payment, or the biggest regular one) a month late.
- supplier_up: the biggest regular supplier payment 10% dearer.
- surprise_bill: an unexpected bill the size of a month's rent next week (a week of spending if
  there's no rent).
A surprise that the numbers can't build (no sales, no supplier paid regularly…) is left out.
"""

from __future__ import annotations

from datetime import date, timedelta

from aheadly.ai.forecast_engine import expand_scheduled_items
from aheadly.ai.templates import payment_name
from aheadly.domain import ScheduledItem

SALES_DROP = 20  # percent
SALES_WEEKS = 4
LATE_DAYS = 30
SUPPLIER_RISE = 10  # percent
BILL_IN_DAYS = 7


def _name(item: ScheduledItem) -> str:
    """The payment as the owner knows it, without the bank's wording (roadmap 4.2)."""
    return payment_name(item.label, item.category, item.source == "statement")


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"


def _money(x: float) -> str:
    return f"${abs(x):,.0f}"


def _active(items: list[ScheduledItem]) -> list[ScheduledItem]:
    return [i for i in items if i.active and not i.paused and i.source != "scenario"]


def surprises(
    items: list[ScheduledItem],
    today: date,
    end: date,
    weekly_sales: float,
    monthly_outflow: float,
    replaced: set | frozenset = frozenset(),
) -> list[dict]:
    """`replaced`: statement occurrences (item id, n-th time) a payment the owner told us about stands
    in for; a surprise on one of those would change nothing."""
    found = []
    if weekly_sales > 0:
        found.append(
            {
                "key": "sales_drop",
                "label": f"Sales {SALES_DROP}% lower for {SALES_WEEKS} weeks",
                "detail": f"About {_money(weekly_sales * SALES_DROP / 100)} less coming in each week.",
                "adjustments": [
                    {
                        "type": "revenue_change",
                        "percent": -SALES_DROP,
                        "start_date": today.isoformat(),
                        "weeks": SALES_WEEKS,
                    }
                ],
            }
        )

    coming = []
    for item in _active(items):
        # money the business counts on (not a "maybe" like an insurer's claims, whose arrival the
        # forecast already doubts)
        if item.amount > 0 and item.certainty != "maybe" and item.likelihood >= 1:
            events = expand_scheduled_items([item], today, end)
            if events:
                coming.append((len(events) == 1, item.amount, item, events[0][0]))
    if coming:
        _, _, item, when = max(coming, key=lambda c: (c[0], c[1]))  # one big payment first
        found.append(
            {
                "key": "late_customer",
                "label": "Your biggest payment coming in arrives a month late",
                "detail": f"{_name(item)}: {_money(item.amount)} due {_day(when)}, arriving "
                f"{_day(when + timedelta(days=LATE_DAYS))} instead.",
                "adjustments": [
                    {
                        "type": "move_item",
                        "label": item.label,
                        "new_date": (when + timedelta(days=LATE_DAYS)).isoformat(),
                    }
                ],
            }
        )

    suppliers = [
        i
        for i in _active(items)
        if i.category == "suppliers"
        and i.recurrence
        and i.amount < 0
        and any((i.id, k) not in replaced for k, _ in enumerate(expand_scheduled_items([i], today, end)))
    ]
    if suppliers:
        item = min(suppliers, key=lambda i: i.amount)
        found.append(
            {
                "key": "supplier_up",
                "label": f"Your main supplier charges {SUPPLIER_RISE}% more",
                "detail": f"{_name(item)}: {_money(item.amount)} → "
                f"{_money(item.amount * (1 + SUPPLIER_RISE / 100))} each time.",
                "adjustments": [
                    {
                        "type": "recurring_change",
                        "label": item.label,
                        "amount_delta": round(item.amount * SUPPLIER_RISE / 100, 2),
                        "start_date": today.isoformat(),
                    }
                ],
            }
        )

    rents = [i for i in _active(items) if i.category == "rent" and i.recurrence and i.amount < 0]
    amount = -min(rents, key=lambda i: i.amount).amount if rents else monthly_outflow * 12 / 52
    amount = round(amount / 10) * 10
    if amount > 0:
        size = "a month's rent" if rents else "a week's spending"
        found.append(
            {
                "key": "surprise_bill",
                "label": "A surprise bill next week",
                "detail": f"{_money(amount)} on {_day(today + timedelta(days=BILL_IN_DAYS))}, the size of {size}.",
                "adjustments": [
                    {
                        "type": "one_time_expense",
                        "amount": amount,
                        "date": (today + timedelta(days=BILL_IN_DAYS)).isoformat(),
                        "label": "Surprise bill",
                    }
                ],
            }
        )
    return found
