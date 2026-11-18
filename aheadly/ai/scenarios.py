"""What-if scenarios: apply adjustments to the list of scheduled items.

The Forecast Engine does not know about scenarios; it just receives a different
list of scheduled items. All adjustment types are pure functions on that list.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from aheadly.core.financing import loan_payments
from aheadly.domain import Adjustment, ScheduledItem

ADJUSTMENT_TYPES = (
    "one_time_expense",  # {amount, date, label}
    "move_item",  # {label, new_date}
    "remove_item",  # {label}
    "recurring_change",  # {label, amount_delta, recurrence, start_date}
    "revenue_change",  # {percent, start_date, weeks?}  (a weekly line; `weeks` ends it, roadmap 3.5)
    "collect_early",  # {label, new_date}
    "split_item",  # {label, new_date, share?}  (part stays, the rest moves; roadmap 3.7)
    "financing",  # {amount, start_date, repay_date, cost, label}  (money in, then back with its cost; 3.6)
    "loan",  # {amount, start_date, yearly_rate, months, fees, label}  (money in, monthly payments; R.2)
)


REQUIRED = {
    "one_time_expense": ("amount",),
    "move_item": ("label", "new_date"),
    "collect_early": ("label", "new_date"),
    "split_item": ("label", "new_date"),
    "remove_item": ("label",),
    "recurring_change": ("label", "amount_delta"),
    "revenue_change": ("percent",),
}
REQUIRED_HELP = {
    "amount": "the amount in dollars.",
    "label": "the name of the payment, as in the business's scheduled items.",
    "new_date": "the new day as YYYY-MM-DD (or 'next_month' for a move to next month with no day).",
    "amount_delta": "the change per payment in dollars (negative: less money).",
    "percent": "the change in percent (+10: sales up 10%).",
}


def parse_adjustment(raw: dict) -> Adjustment:
    """LBYL validation of an adjustment coming from the LLM or the form."""
    kind = raw.get("type")
    if kind not in ADJUSTMENT_TYPES:
        raise ValueError(f"Unknown adjustment type '{kind}'. Use one of {ADJUSTMENT_TYPES}.")
    params = {k: v for k, v in raw.items() if k != "type"}
    missing = [field for field in REQUIRED.get(kind, ()) if params.get(field) in (None, "")]
    if missing:  # said in words the model can act on (the Gemini run got "'new_date'")
        raise ValueError(f"{kind} needs {' and '.join(missing)}: {REQUIRED_HELP[missing[0]]}")
    if kind == "split_item" and not 0 < float(params.get("share", 0.5)) < 1:
        raise ValueError("split_item needs a share between 0 and 1 (0.5: half moves to new_date)")
    if kind == "one_time_expense" and float(params.get("amount", 0)) <= 0:
        raise ValueError("one_time_expense needs a positive amount")
    if kind == "financing":
        if float(params.get("amount", 0)) <= 0:
            raise ValueError("financing needs a positive amount")
        if not params.get("start_date") or not params.get("repay_date"):
            raise ValueError("financing needs the day the money comes in and the day it's paid back")
        if float(params.get("cost", 0)) < 0:
            raise ValueError("financing can't cost less than nothing")
    if kind == "loan":
        if float(params.get("amount", 0)) <= 0:
            raise ValueError("A loan needs a positive amount.")
        if not 1 <= int(params.get("months", 0)) <= 120:
            raise ValueError("A loan is paid back in 1 to 120 months.")
        if not 0 <= float(params.get("yearly_rate", 0)) <= 100:
            raise ValueError("The yearly rate is between 0% and 100%.")
        if float(params.get("fees", 0)) < 0 or not params.get("start_date"):
            raise ValueError("A loan needs the day the money comes in, and fees can't be negative.")
    for key in ("date", "new_date", "start_date", "repay_date"):
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
    if adj.type == "loan":  # roadmap R.2: the owner's own numbers; payments past the 8 weeks don't show
        name = p.get("label") or "Loan"
        start, fees = p["start_date"], float(p.get("fees", 0))
        lines = [ScheduledItem(name, abs(float(p["amount"])), start, kind="other", source="scenario")]
        if fees:
            lines.append(
                ScheduledItem(f"{name} fees", -round(fees, 2), start, kind="other", source="scenario")
            )
        schedule = loan_payments(float(p["amount"]), float(p.get("yearly_rate", 0)), int(p["months"]), start)
        return (
            items
            + lines
            + [
                ScheduledItem(f"{name} payment", -pay, when, kind="other", source="scenario")
                for when, pay in schedule
            ]
        )
    if adj.type == "financing":
        name = p.get("label", "Financing")
        amount = abs(float(p["amount"]))
        if p["repay_date"] <= p["start_date"]:
            raise ValueError("The money has to be paid back after it comes in.")
        return items + [
            ScheduledItem(name, amount, p["start_date"], kind="other", source="scenario"),
            ScheduledItem(
                f"{name} paid back",
                -round(amount + float(p.get("cost", 0)), 2),
                p["repay_date"],
                kind="other",
                source="scenario",
            ),
        ]
    if adj.type in ("move_item", "collect_early"):
        target = _find(items, p["label"])
        target.due_date = p["new_date"]
        target.user_edited = True  # a later upload must not undo the owner's plan
        return items
    if adj.type == "split_item":  # roadmap 3.7: part stays on its date, the rest is paid later
        target = _find(items, p["label"])
        part = round(target.amount * float(p.get("share", 0.5)), 2)
        target.amount = round(target.amount - part, 2)
        target.user_edited = True
        return items + [
            ScheduledItem(
                f"{target.label} (second part)",
                part,
                p["new_date"],
                kind=target.kind,
                source="scenario",
                category=target.category,
            )
        ]
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
    names = sorted({item.label for item in items})
    raise ValueError(
        f"No scheduled item matches '{label}'. Use one of these names as the label: " + "; ".join(names)
    )


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
