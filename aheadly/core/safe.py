"""Safe to spend and a safe pay for the owner (roadmap 3.4).

Safe to spend now: every scenario drops by the same amount when the owner spends it today, so the
worst case (10th percentile) drops by exactly that amount on every day ahead. The biggest safe
amount is therefore the lowest worst-case balance in the horizon (or today's cash, if lower) minus
the low cash line: no search needed. Rounded down to $10.

Safe pay for the owner: a change of pay lands on the pay days only, and a pay that varies may move
differently in each scenario, so it is found by testing amounts as what-ifs (halving the range
each time, 14 tries, to within $10).
"""

from __future__ import annotations

import math
from typing import Callable

from aheadly.domain import ForecastResult, ScheduledItem

STEP = 10  # dollars
TRIES = 14

WorstAfter = Callable[[float], float]  # new pay per payment → lowest worst case with it


def _down(value: float) -> int:
    return max(0, int(math.floor(value / STEP) * STEP))


def safe_to_spend(forecast: ForecastResult, low_cash_line: float) -> dict:
    lowest_worst = min(forecast.min_p10, forecast.opening_balance)
    room = lowest_worst - low_cash_line
    return {
        "amount": _down(room),
        "low_cash_line": round(low_cash_line),
        "lowest_worst_case": round(lowest_worst),
        "reason": "already_below" if room <= 0 else "ok",
    }


def owner_pay_item(items: list[ScheduledItem]) -> ScheduledItem | None:
    """The owner's regular pay, once the owner said which transfer it is (the biggest, if several)."""
    pays = [
        i
        for i in items
        if i.active and not i.paused and i.category == "owner_pay" and i.recurrence and i.amount < 0
    ]
    return min(pays, key=lambda i: i.amount, default=None)


def safe_owner_pay(
    item: ScheduledItem, low_cash_line: float, worst_after: WorstAfter, headroom: float
) -> int:
    """Biggest pay per payment that keeps the worst case at or above the line (0 if even no pay
    doesn't). `headroom`: how far above the line the worst case is today (an upper bound to try)."""
    now = -item.amount
    if worst_after(0.0) < low_cash_line:
        return 0
    low, high = 0.0, now + max(0.0, headroom) + STEP
    for _ in range(TRIES):
        mid = (low + high) / 2
        if worst_after(mid) >= low_cash_line:
            low = mid
        else:
            high = mid
    return _down(low)
