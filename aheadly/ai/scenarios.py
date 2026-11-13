"""What-if scenarios: apply adjustments to the list of scheduled items.

The Forecast Engine does not know about scenarios; it just receives a different
list of scheduled items. All adjustment types are pure functions on that list.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from aheadly.domain import Adjustment, ScheduledItem

ADJUSTMENT_TYPES = (
    "one_time_expense",  # {amount, date, label}
    "move_item",  # {label, new_date}
    "remove_item",  # {label}
    "recurring_change",  # {label, amount_delta, recurrence, start_date}
    "revenue_change",  # {percent, start_date, weeks?}  (a weekly line; `weeks` ends it, roadmap 3.5)
    "collect_early",  # {label, new_date}
)


def parse_adjustment(raw: dict) -> Adjustment:
    """LBYL validation of an adjustment coming from the LLM or the form."""
    kind = raw.get("type")
    if kind not in ADJUSTMENT_TYPES:
        raise ValueError(f"Unknown adjustment type '{kind}'. Use one of {ADJUSTMENT_TYPES}.")
    params = {k: v for k, v in raw.items() if k != "type"}
    if kind == "one_time_expense" and float(params.get("amount", 0)) <= 0:
        raise ValueError("one_time_expense needs a positive amount")
    if kind in ("move_item", "collect_early", "remove_item", "recurring_change") and not params.get("label"):
        raise ValueError(f"{kind} needs a label")
    for key in ("date", "new_date", "start_date"):
        if key in params and params[key]:
            params[key] = date.fromisoformat(str(params[key]))
    return Adjustment(type=kind, params=params)


def apply_adjustments(
    items: list[ScheduledItem],
    adjustments: list[Adjustment],
    today: date,
    horizon_days: int = 56,
    weekly_sales: float = 0.0,
) -> list[ScheduledItem]:
    """`weekly_sales`: the business's real average weekly sales, which a revenue change is a percent of."""
    result = [replace(item) for item in items]
    for adjustment in adjustments:
        result = _apply_one(result, adjustment, today, horizon_days, weekly_sales)
    return result


def _apply_one(
    items: list[ScheduledItem], adj: Adjustment, today: date, horizon_days: int, weekly_sales: float
) -> list[ScheduledItem]:
    p = adj.params
    if adj.type == "one_time_expense":
        return items + [
            ScheduledItem(
                p.get("label", "New expense"),
                -abs(float(p["amount"])),
                p.get("date") or today,
                kind="planned_purchase",
                source="scenario",
            )
        ]
    if adj.type in ("move_item", "collect_early"):
        target = _find(items, p["label"])
        target.due_date = p["new_date"]
        target.user_edited = True  # a later upload must not undo the owner's plan
        return items
    if adj.type == "remove_item":
        target = _find(items, p["label"])
        target.active = False
        target.user_edited = True
        return items
    if adj.type == "recurring_change":
        target = _find(items, p["label"])
        target.amount += float(p["amount_delta"])
        target.user_edited = True
        if p.get("start_date"):
            target.due_date = max(target.due_date, p["start_date"])
        return items
    if adj.type == "revenue_change":
        if weekly_sales <= 0:
            raise ValueError("There are no sales in your statement yet to change.")
        return items + _revenue_change_items(
            float(p["percent"]),
            p.get("start_date") or today,
            today,
            horizon_days,
            weekly_sales,
            int(p["weeks"]) if p.get("weeks") else None,
        )
    raise ValueError(f"Unhandled adjustment type {adj.type}")


def _find(items: list[ScheduledItem], label: str) -> ScheduledItem:
    needle = label.lower().strip()
    for item in items:  # the exact name first: "Inventory" must not move "Inventory restock"
        if item.label.lower().strip() == needle:
            return item
    for item in items:
        if needle in item.label.lower() or item.label.lower() in needle:
            return item
    raise ValueError(f"No scheduled item matches '{label}'")


def _revenue_change_items(
    percent: float,
    start: date,
    today: date,
    horizon_days: int,
    weekly_sales: float,
    weeks: int | None = None,
) -> list[ScheduledItem]:
    """Model a sales change as one weekly adjustment line (simple, explainable), for `weeks` weeks
    if given (a stress test's "20% lower for 4 weeks"), else from then on."""
    weekly_delta = weekly_sales * percent / 100.0
    first = max(start, today) + timedelta(days=6)
    return [
        ScheduledItem(
            f"Sales change {percent:+.0f}%",
            round(weekly_delta, 2),
            first,
            kind="other",
            recurrence="weekly",
            source="scenario",
            end_date=first + timedelta(days=7 * (weeks - 1)) if weeks else None,
        )
    ]
