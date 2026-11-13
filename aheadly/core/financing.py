"""Financing helper (roadmap 3.6): is the gap about timing or about the business losing money, and
what would each of the owner's own ways to cover it cost?

Only options the owner says they already have are compared; nothing is offered and no lender is
named. Rates and fees come from the owner. Every number is computed here; the model only words it.

- gap(): how far below the line the base case (or, if it never dips, a bad month) goes, when it starts
  and when the base case is back above the line.
- verdict(): "none" (even a bad month stays above the line), "timing" (normal weeks bring in more than
  goes out and the base case recovers within the horizon) or "structural" (it doesn't: borrowing only
  delays the problem).
- plan(): one option turned into what-if adjustments, with its cost in dollars and as a yearly rate.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from aheadly.domain import ForecastResult

# the owner's own options; "fields" are what the form asks for
KINDS: dict[str, dict] = {
    "credit_line": {"label": "Credit line", "fields": ("limit", "rate", "fee")},
    "card": {"label": "Business credit card", "fields": ("limit", "rate")},
    "loan": {"label": "Short-term loan", "fields": ("limit", "rate", "fee", "arrive_days")},
    "supplier_terms": {"label": "Longer supplier terms", "fields": ("payment", "extra_days", "fee")},
    "invoice_early": {"label": "Getting paid early on an invoice", "fields": ("payment", "fee_pct")},
    "own_money": {"label": "Your own money", "fields": ("limit",)},
}
BORROWING = ("credit_line", "card", "loan", "own_money")
ROUND_TO = 100  # the amount to cover is rounded up to this


def check_option(raw: dict) -> dict:
    """An option as the owner typed it, checked (ValueError with a plain message if not usable)."""
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ValueError("Pick what kind of option this is.")
    option = {"kind": kind}
    for field in KINDS[kind]["fields"]:
        value = raw.get(field)
        if field == "payment":
            if not value:
                raise ValueError("Pick which payment this is about.")
            option[field] = str(value)
            continue
        value = float(value or 0)
        if value < 0:
            raise ValueError("Amounts, rates and days can't be negative.")
        option[field] = value
    if kind in BORROWING and option["limit"] <= 0:
        raise ValueError("Say how much you could get (the limit or amount).")
    if kind in ("credit_line", "card", "loan") and option["rate"] <= 0:
        raise ValueError("Add the yearly interest rate your bank gave you, so the cost can be worked out.")
    if kind == "supplier_terms" and option["extra_days"] <= 0:
        raise ValueError("Say how many more days the supplier would give you.")
    if raw.get("name"):
        option["name"] = str(raw["name"]).strip()
    return option


def label(option: dict) -> str:
    base = option.get("name") or KINDS[option["kind"]]["label"]
    if option["kind"] in ("supplier_terms", "invoice_early"):
        return f"{base}: {option['payment']}"
    return base


def gap(forecast: ForecastResult, line: float) -> dict:
    """How short, from when, until when. `base`/`worst` are dollars below the line (0 = not short).
    `start` is the first day below the line (base case, or a bad month if the base case never dips);
    `low_date` the lowest day of that case; `recovery` the day the base case is back above the line
    for good (None if it isn't within the horizon, or never dipped)."""
    points = forecast.points
    base_low = min(points, key=lambda p: p.balance_p50)
    worst_low = min(points, key=lambda p: p.balance_p10)
    base_short = max(0.0, line - base_low.balance_p50)
    worst_short = max(0.0, line - worst_low.balance_p10)
    if base_short > 0:
        below = [p.date for p in points if p.balance_p50 < line]
        start, low_date = below[0], base_low.date
        after = [p for p in points if p.date > below[-1]]
        recovery = after[0].date if after else None
    elif worst_short > 0:
        start = next(p.date for p in points if p.balance_p10 < line)
        low_date, recovery = worst_low.date, None
    else:
        start = low_date = recovery = None
    return {
        "base": round(base_short),
        "worst": round(worst_short),
        "base_dips": base_short > 0,
        "start": start,
        "low_date": low_date,
        "recovery": recovery,
    }


def regular_weekly(start_balance: float, end_base: float, one_offs: float, weeks: int) -> float:
    """What a normal week adds or takes away over the horizon in the base case, once the one-off
    payments the forecast knows about (in and out) are left out."""
    return round((end_base - start_balance - one_offs) / weeks, 2)


def verdict(g: dict, regular: float) -> str:
    if g["worst"] <= 0:
        return "none"
    if regular <= 0:
        return "structural"
    if g["base_dips"] and g["recovery"] is None:
        return "structural"
    return "timing"


def amount_needed(g: dict) -> int:
    short = g["base"] if g["base"] > 0 else g["worst"]
    return int(math.ceil(short / ROUND_TO) * ROUND_TO)


def repay_date(forecast: ForecastResult, line: float, after: date, cost: float) -> date | None:
    """The first day after `after` from which the base case, less the cost, stays above the line to the
    end of the horizon: repaying then doesn't open a new gap. None if there's no such day."""
    points = [p for p in forecast.points if p.date > after]
    for i, p in enumerate(points):
        if all(q.balance_p50 - cost >= line for q in points[i:]):
            return p.date
    return None


def cost(amount: float, rate: float, days: int, fee: float = 0.0) -> float:
    """Simple interest for the days used, plus fees: amount × rate × days / 365 + fees."""
    return round(amount * rate / 100 * max(days, 1) / 365 + fee, 2)


def yearly_rate(amount: float, dollars: float, days: int) -> float:
    """What the cost comes to as a yearly rate (so a 2% fee for 30 days compares with a 24% line)."""
    if amount <= 0 or days <= 0:
        return 0.0
    return round(dollars / amount * 365 / days * 100, 1)


def plan(
    option: dict,
    need: int,
    g: dict,
    forecast: ForecastResult,
    line: float,
    today: date,
    payments: dict[str, tuple[float, date]],
) -> dict:
    """One option as adjustments plus its cost. `payments`: label → (amount, date) of the dated
    payments in the horizon (for supplier terms and early invoices). `feasible` False comes with a
    plain `reason`; the what-if run (in App Core) then says whether it really covers the gap."""
    kind = option["kind"]
    name = label(option)
    out = {"kind": kind, "label": name, "option": option, "feasible": True, "reason": ""}

    def problem(reason: str) -> None:  # the first problem found is the one to tell the owner
        if out["feasible"]:
            out.update(feasible=False, reason=reason)

    take = max(today, g["start"] - timedelta(days=1))  # the money is needed the day before
    if kind in BORROWING:
        arrives = today + timedelta(days=int(option.get("arrive_days", 0)))
        amount = min(float(need), option["limit"])
        if option["limit"] < need:
            problem("limit")
        if arrives > take:
            take = arrives
            if arrives >= g["start"]:
                problem("late")
        rate = option.get("rate", 0.0)
        fee = option.get("fee", 0.0)
        # repay as soon as the base case can take it; the cost depends on the days, so settle both
        after = max(g["low_date"], take)
        repay = repay_date(forecast, line, after, fee)
        for _ in range(3):
            if repay is None:
                break
            dollars = cost(amount, rate, (repay - take).days, fee)
            better = repay_date(forecast, line, after, dollars)
            if better == repay or better is None:
                break
            repay = better
        if repay is None:
            problem("repay")
            repay = max(forecast.points[-1].date, take + timedelta(days=1))
        days = (repay - take).days
        dollars = cost(amount, rate, days, fee) if kind != "own_money" else 0.0
        out.update(
            amount=round(amount),
            take=take,
            repay=repay,
            days=days,
            cost=round(dollars, 2),
            yearly_rate=yearly_rate(amount, dollars, days),
            adjustments=[
                {
                    "type": "financing",
                    "amount": round(amount, 2),
                    "start_date": take.isoformat(),
                    "repay_date": repay.isoformat(),
                    "cost": round(dollars, 2),
                    "label": name,
                }
            ],
        )
        return out
    found = payments.get(option["payment"])
    if found is None:
        problem("no_payment")
        out.update(amount=0, cost=0.0, yearly_rate=0.0, adjustments=[])
        return out
    amount, due = found
    if kind == "supplier_terms":
        days = int(option["extra_days"])
        new = due + timedelta(days=days)
        dollars = option.get("fee", 0.0)
        adjustments = [{"type": "move_item", "label": option["payment"], "new_date": new.isoformat()}]
        if dollars > 0:
            adjustments.append(
                {
                    "type": "one_time_expense",
                    "amount": dollars,
                    "date": new.isoformat(),
                    "label": f"{name} fee",
                }
            )
        if due > g["low_date"]:
            problem("after_gap")
        out.update(
            amount=round(abs(amount)),
            take=due,
            repay=new,
            days=days,
            cost=round(dollars, 2),
            yearly_rate=yearly_rate(abs(amount), dollars, days),
            adjustments=adjustments,
        )
        return out
    # invoice_early: the money arrives the day before the gap, less the fee
    days = (due - take).days
    dollars = round(abs(amount) * option["fee_pct"] / 100, 2)
    adjustments = [{"type": "collect_early", "label": option["payment"], "new_date": take.isoformat()}]
    if dollars > 0:
        adjustments.append(
            {"type": "one_time_expense", "amount": dollars, "date": take.isoformat(), "label": f"{name} fee"}
        )
    if days <= 0:
        problem("already_early")
    out.update(
        amount=round(abs(amount)),
        take=take,
        repay=due,
        days=max(days, 0),
        cost=dollars,
        yearly_rate=yearly_rate(abs(amount), dollars, days),
        adjustments=adjustments,
    )
    return out


def rank_key(p: dict) -> tuple:
    """Usable and covering first, then the cheapest, then the one that leaves the most room."""
    covers = p.get("impact", {}).get("covers", False)
    return (not p["feasible"], not covers, p["cost"], -p.get("impact", {}).get("lowest_after", 0))
