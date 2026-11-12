"""Busy and slow months (roadmap 2.7).

The forecast model only knows the weekly rhythm of the last few months, so on its own it expects
December to look like October. The owner says which months are busy or slow; for each one this
module measures how its money in compared with a normal month the last time it happened (from the
owner's own statement), and the forecast adds that difference to every day of the month. The owner
can replace our measure with their own ("about 50% more in December"). Without the owner's answer
nothing changes: one year of data is too little to guess the seasons alone (DECISIONS #30).

Money in, not the net flow: last year's one-off purchases (Christmas ingredients) would otherwise
make a busy month look normal.
"""

from __future__ import annotations

import calendar

import pandas as pd

MONTH_NAMES = {m: calendar.month_name[m] for m in range(1, 13)}
RECENT_DAYS = 56  # the window the forecast model learns its level from
LIMITS = (-0.7, 2.0)  # a month at least 30% of normal and at most three times normal


def daily_money_in(flows: pd.DataFrame) -> pd.Series:
    """Money in per calendar day (days without lines count as 0), with the biggest days capped at
    the 95th percentile so one large one-off payment doesn't turn a month into a "busy" one."""
    if flows.empty:
        return pd.Series(dtype=float)
    series = flows.set_index("date")["money_in"].astype(float)
    full = pd.date_range(series.index.min(), series.index.max(), freq="D")
    series = series.reindex(full, fill_value=0.0)
    return series.clip(upper=series.quantile(0.95))


def recent_level(money_in: pd.Series) -> float:
    """Typical money in per day over the window the forecast model learns from."""
    return float(money_in.tail(RECENT_DAYS).mean()) if len(money_in) else 0.0


def month_estimates(money_in: pd.Series, busy: list[int], slow: list[int]) -> dict[int, float | None]:
    """For each busy or slow month: how much more (+0.33) or less (−0.15) money came in than in a
    normal month, the last time it was in the statement. None when the statement doesn't cover it,
    or covers too few normal months to compare with."""
    marked = set(busy) | set(slow)
    if not len(money_in):
        return {m: None for m in marked}
    by_month = money_in.groupby([money_in.index.year, money_in.index.month]).mean()
    normal = [level for (_, month), level in by_month.items() if month not in marked]
    if len(normal) < 3 or sum(normal) <= 0:
        return {m: None for m in marked}
    base = sum(normal) / len(normal)
    out: dict[int, float | None] = {}
    for month in sorted(marked):
        levels = [level for (_, m), level in by_month.items() if m == month]
        out[month] = clamp(levels[-1] / base - 1) if levels else None
    return out


def clamp(change: float) -> float:
    return round(min(max(change, LIMITS[0]), LIMITS[1]), 2)


def daily_shift(level: float, changes: dict[int, float]) -> dict[int, float]:
    """Extra money in per day for each month (negative for a slow month), from today's level."""
    return {month: round(level * change, 2) for month, change in changes.items() if change}
