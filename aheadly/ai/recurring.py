"""Roadmap 2.3: find the payments and income that repeat, and put them on their real dates.

A bakery's statement has a rhythm: card sales every day, payroll every Friday, rent on the 15th,
the gas bill around the 6th, the flour order every quarter, the December bonus. A forecast model
that only knows "weekly seasonality" smears the rent over every day of the month; this module finds
each repeating payee and the calendar rule it follows, so the forecast can put it on its day.

How (DECISIONS #30):
1. Group lines by payee (`match_key`: the description in plain form; lines that differ only in a
   reference number are grouped by the description with numbers masked) and by direction.
2. From the gaps between dates, try the rule that fits: some weekdays every week (daily, twice a
   week, weekly), every two weeks, a day of the month (or its last business day), twice a month,
   every 2, 3, 6 or 12 months.
3. The amount is fixed if the last three differ by less than 15%, otherwise it "varies" and the
   median of the last three is used.
4. What goes into the forecast as a dated item (`scheduled`): everything monthly or rarer, and
   weekly items with a fixed amount. Daily and weekly flows whose amount varies (card sales, weekly
   supplier orders) stay in the history the model learns from: it handles them well and its
   uncertainty band comes from them.

Weekends move to the next (or previous) business day as the payee did in the past; public holidays
are not known here.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from aheadly.data.connectors.csv_connector import plain

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
EVERY_N_MONTHS = {2: "every 2 months", 3: "quarterly", 6: "twice a year", 12: "yearly"}
INTERNAL_CATEGORIES = {"transfer_internal", "card_payment"}


@dataclass(frozen=True)
class TxLine:
    id: int
    date: date
    amount: float
    description: str
    category: str | None
    is_internal: bool


@dataclass
class Recurring:
    """One repeating payee and the rule it follows."""

    match_key: str
    label: str
    direction: str  # in | out
    category: str
    cadence: str  # daily, weekly, twice a week, every two weeks, monthly, twice a month, quarterly...
    rules: list[str]  # recurrence rules for the forecast, one item per rule (see next_dates)
    next_dates: list[date]  # first upcoming date of each rule (nominal, before the weekend shift)
    amount: float  # signed, per occurrence
    amount_varies: bool
    occurrences: int
    last_date: date
    transaction_ids: list[int] = field(default_factory=list)
    certainty: str = "confirmed"  # maybe: seen only twice (quarterly, twice a year, yearly)
    internal: bool = False  # a move between the owner's own accounts or a card payment
    missed: bool = False  # the last expected one hasn't arrived (5 days late)
    amount_changed: bool = False  # fixed amount, but the last one differs > 5% from the one before

    seasonal: bool = False  # only some months of the year (temporary staff for Halloween)

    @property
    def scheduled(self) -> bool:
        """Goes into the forecast as dated items (else it stays in the model's history)."""
        if self.internal or self.seasonal:
            return False
        frequent = self.cadence in ("daily", "weekly", "twice a week") or self.cadence.endswith("a week")
        return not (frequent and self.amount_varies)


# ------------------------------------------------------------- calendar helpers
def _month_add(year: int, month: int, n: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + n
    return index // 12, index % 12 + 1


def _last_day(year: int, month: int) -> int:
    y, m = _month_add(year, month, 1)
    return (date(y, m, 1) - timedelta(days=1)).day


def _last_business_day(year: int, month: int) -> date:
    d = date(year, month, _last_day(year, month))
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def nominal_date(year: int, month: int, day: str) -> date:
    """The day a rule names in a month, before any weekend shift. `day`: '15', 'last_bd' or 'last'."""
    if day in ("last_bd", "last"):
        return date(year, month, _last_day(year, month))
    return date(year, month, min(int(day), _last_day(year, month)))


def business_day(d: date, shift: str, day: str = "") -> date:
    """Move a weekend date to the next business day (or the previous one)."""
    if day == "last_bd":
        shift = "prev"
    if day == "last" or shift == "none":
        return d
    step = -1 if shift == "prev" else 1
    while d.weekday() >= 5:
        d += timedelta(days=step)
    return d


def month_rule(day: str, shift: str, every: int) -> str:
    return f"month_day:{day}:{shift}:{every}"


def parse_month_rule(rule: str) -> tuple[str, str, int]:
    _, day, shift, every = rule.split(":")
    return day, shift, int(every)


def month_rule_dates(rule: str, due: date, end: date) -> list[date]:
    """Dated events of a `month_day` rule from `due` (the next one, possibly moved by the owner) to
    `end`: `due` itself (on a business day), then the rule's day every N months after it."""
    day, shift, every = parse_month_rule(rule)
    events = [business_day(due, shift, day)]
    k = 1
    while True:
        y, m = _month_add(due.year, due.month, every * k)
        event = business_day(nominal_date(y, m, day), shift, day)
        if event > end:
            break
        events.append(event)
        k += 1
    return [e for e in events if e <= end]


# ------------------------------------------------------------- grouping
def _masked(key: str) -> str:
    return re.sub(r"\S*\d\S*", "#", key)


def group_lines(lines: list[TxLine]) -> dict[tuple[str, str], list[TxLine]]:
    """(match_key, direction) → lines. Lines whose descriptions differ only by a reference number
    ("TRANSF NEQUI REF 51234", "... REF 77812") are one group; a description that repeats exactly
    ("TRANSF 0045 REF 88213") keeps its number."""
    exact: dict[tuple[str, str], list[TxLine]] = defaultdict(list)
    for line in lines:
        exact[(plain(line.description), "in" if line.amount > 0 else "out")].append(line)
    by_mask: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for key, direction in exact:
        by_mask[(_masked(key), direction)].append((key, direction))
    groups: dict[tuple[str, str], list[TxLine]] = {}
    for (mask, direction), keys in by_mask.items():
        largest = max(len(exact[k]) for k in keys)
        total = sum(len(exact[k]) for k in keys)
        if len(keys) >= 3 and largest < 0.5 * total:
            groups[(mask, direction)] = [line for k in keys for line in exact[k]]
        else:
            for k in keys:
                groups[k] = exact[k]
    return groups


# ------------------------------------------------------------- detection
def detect(lines: list[TxLine], today: date) -> list[Recurring]:
    """Every repeating payee in `lines`, with its rule and next dates on or after `today`."""
    found = []
    for (key, direction), members in group_lines(lines).items():
        result = _detect_group(key, direction, members, today)
        if result is not None:
            found.append(result)
    return sorted(found, key=lambda r: (r.next_dates[0] if r.next_dates else today, r.match_key))


def _daily_amounts(members: list[TxLine]) -> dict[date, float]:
    per_day: dict[date, float] = defaultdict(float)
    for line in members:
        per_day[line.date] += line.amount
    return dict(sorted(per_day.items()))


def _detect_group(key: str, direction: str, members: list[TxLine], today: date) -> Recurring | None:
    per_day = _daily_amounts(members)
    days = list(per_day)
    if len(days) < 2:
        return None
    categories = [m.category for m in members if m.category]
    category = statistics.mode(categories) if categories else "other"
    # staff are paid on the business day before a weekend; bills are paid on the one after
    shift = "prev" if category == "payroll" else "next"
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    median_gap = statistics.median(gaps)
    pattern = None
    if median_gap <= 10:
        pattern = _weekdays(days, gaps)
    if pattern is None and 11 <= median_gap <= 17:
        pattern = _every_two_weeks(days, gaps)
    if pattern is None and 8 <= median_gap <= 22:
        pattern = _twice_a_month(days, shift)
    if pattern is None and 24 <= median_gap <= 38:
        pattern = _monthly(days, shift)
    if pattern is None:
        pattern = _every_n_months(days, gaps, shift)
    if pattern is None:
        return None
    cadence, rules, period = pattern
    last = days[-1]
    # long breaks inside the year: it happens in some months only
    seasonal = period <= 31 and max(gaps[-24:]) > 4 * period
    # stopped: nothing for more than two periods (an old account, a supplier dropped)
    if (today - last).days > 2 * period + 5:
        return None
    if len(days) < (2 if period >= 80 else 3):
        return None

    recent = [per_day[d] for d in days[-3:]]
    window = [per_day[d] for d in days[-6:]]
    spread = (max(window) - min(window)) / max(abs(statistics.median(window)), 0.01)
    varies = spread > 0.15
    amount = statistics.median(recent) if varies else recent[-1]
    changed = (not varies) and len(recent) >= 2 and abs(recent[-1] - recent[-2]) > 0.05 * abs(recent[-2])

    next_dates = [_next_nominal(rule, days, today) for rule in rules]
    # the one after the last seen (half a period later, so a payment a day early isn't expected again)
    expected = _next_nominal(rules[0], days, last + timedelta(days=max(3, period // 2)))
    missed = _shifted(rules[0], expected) + timedelta(days=5) < today

    latest = max(members, key=lambda m: (m.date, m.id))
    internal = any(m.is_internal for m in members) or category in INTERNAL_CATEGORIES
    return Recurring(
        match_key=key,
        label=_label(latest.description),
        direction=direction,
        category=category,
        cadence=cadence,
        rules=rules,
        next_dates=next_dates,
        amount=round(amount, 2),
        amount_varies=varies,
        occurrences=len(days),
        last_date=last,
        transaction_ids=[m.id for m in members],
        certainty="maybe" if len(days) < 3 else "confirmed",
        internal=internal,
        missed=missed,
        amount_changed=changed,
        seasonal=seasonal,
    )


def _label(description: str) -> str:
    text = " ".join(description.split())
    return text[:1].upper() + text[1:].lower() if text.isupper() else text


# ------------------------------------------------------------- the rules
def _weekdays(days: list[date], gaps: list[int]) -> tuple[str, list[str], int] | None:
    """Some weekdays every week: daily (5+ days), twice a week, weekly."""
    recent = [d for d in days if d > days[-1] - timedelta(weeks=26)]
    first_week = recent[0] - timedelta(days=recent[0].weekday())
    weeks = (days[-1] - first_week).days // 7 + 1
    if weeks < 3:
        return None
    seen: dict[int, set[int]] = defaultdict(set)
    for d in recent:
        seen[d.weekday()].add((d - first_week).days // 7)
    weekdays = sorted(w for w, in_weeks in seen.items() if len(in_weeks) >= 0.6 * weeks)
    on_them = sum(1 for d in recent if d.weekday() in weekdays)
    if weekdays and on_them >= 0.8 * len(recent):
        n = len(weekdays)
        cadence = "daily" if n >= 5 else {1: "weekly", 2: "twice a week"}.get(n, f"{n} times a week")
        return cadence, [f"weekday:{w}" for w in weekdays], 7
    near_week = sum(1 for g in gaps[-12:] if 5 <= g <= 9)
    if statistics.median(gaps) >= 5 and near_week >= 0.7 * len(gaps[-12:]):
        return "weekly", [f"weekday:{days[-1].weekday()}"], 7
    return None


def _every_two_weeks(days: list[date], gaps: list[int]) -> tuple[str, list[str], int] | None:
    recent = gaps[-12:]
    fits = sum(1 for g in recent if 13 <= g <= 15)
    same_weekday = statistics.mode([d.weekday() for d in days[-8:]])
    on_weekday = sum(1 for d in days[-8:] if d.weekday() == same_weekday)
    if fits >= 0.8 * len(recent) and on_weekday >= 0.85 * len(days[-8:]):
        return "every two weeks", ["every:14"], 14
    return None


def _months_spanned(days: list[date]) -> list[tuple[int, int]]:
    out = []
    y, m = days[0].year, days[0].month
    while (y, m) <= (days[-1].year, days[-1].month):
        out.append((y, m))
        y, m = _month_add(y, m, 1)
    return out


def _anchor(days: list[date], default_shift: str = "next") -> tuple[str, str] | None:
    """The day of the month a group of dates follows, and how weekends were shifted (when the
    dates don't show it: `default_shift`)."""
    last_bd = sum(1 for d in days if d == _last_business_day(d.year, d.month))
    if last_bd >= 0.7 * len(days):
        return "last_bd", "prev"
    last = sum(1 for d in days if d.day == _last_day(d.year, d.month))
    if last >= 0.7 * len(days):
        return "last", "none"
    doms = [d.day for d in days]
    mode = statistics.mode(doms)
    share = doms.count(mode) / len(doms)
    day = mode if share >= 0.4 else int(statistics.median(doms))
    later = sum(1 for x in doms if x > day)
    earlier = sum(1 for x in doms if x < day)
    if earlier == later:
        return str(day), default_shift
    return str(day), "prev" if earlier > later else "next"


def _monthly(days: list[date], default_shift: str = "next") -> tuple[str, list[str], int] | None:
    months = _months_spanned(days[-13:])
    per_month = defaultdict(int)
    for d in days[-13:]:
        per_month[(d.year, d.month)] += 1
    covered = sum(1 for ym in months if per_month[ym] >= 1)
    doubled = sum(1 for ym in months if per_month[ym] > 1)
    if covered >= 0.7 * len(months) and doubled <= 0.15 * len(months):
        if _drifts(days[-6:]):
            # paid a little later (or earlier) each month: go by the gap, not the day
            gap = int(statistics.median([(b - a).days for a, b in zip(days[-4:], days[-3:])]))
            return "monthly", [f"every:{gap}"], gap
        day, shift = _anchor(days[-13:], default_shift)
        return "monthly", [month_rule(day, shift, 1)], 30
    return None


def _drifts(days: list[date]) -> bool:
    """The day of the month wanders over more than 12 days (counting the 30th and the 2nd as close)."""
    if any(d == _last_business_day(d.year, d.month) for d in days[-3:]):
        return False
    doms = [d.day for d in days]
    shifted = [(x + 15) % 31 for x in doms]
    return min(max(doms) - min(doms), max(shifted) - min(shifted)) > 12


def _twice_a_month(days: list[date], default_shift: str = "next") -> tuple[str, list[str], int] | None:
    recent = days[-26:]
    positions = sorted({(d.day if d != _last_business_day(d.year, d.month) else 31) for d in recent})
    if len(positions) < 2:
        return None
    # split the days of the month at the widest gap between them
    split = max(range(1, len(positions)), key=lambda i: positions[i] - positions[i - 1])
    low = set(positions[:split])
    first = [d for d in recent if d.day in low and d != _last_business_day(d.year, d.month)]
    second = [d for d in recent if d not in first]
    rules = []
    for half in (first, second):
        if len(half) < 3 or _monthly(half) is None:
            return None
        day, shift = _anchor(half, default_shift)
        rules.append(month_rule(day, shift, 1))
    return "twice a month", rules, 15


def _every_n_months(
    days: list[date], gaps: list[int], default_shift: str = "next"
) -> tuple[str, list[str], int] | None:
    median_gap = statistics.median(gaps)
    for n, cadence in EVERY_N_MONTHS.items():
        target = 30.44 * n
        if abs(median_gap - target) > 0.15 * target:
            continue
        fits = sum(1 for g in gaps if abs(g - target) <= 0.2 * target)
        if fits < 0.7 * len(gaps):
            return None
        last = days[-1]
        ny, nm = _month_add(last.year, last.month, n)
        # the same month a year earlier says best which day it falls on (a June/December bonus)
        same_month = [d for d in days if (d.year, d.month) == (ny - 1, nm)]
        day, shift = _anchor(same_month or days, default_shift)
        return cadence, [month_rule(day, shift, n)], int(target)
    return None


# ------------------------------------------------------------- next dates
def _next_nominal(rule: str, days: list[date], start: date) -> date:
    """The first date of `rule` whose (weekend-shifted) day is on or after `start`."""
    last = days[-1]
    if rule.startswith("weekday:"):
        weekday = int(rule.split(":")[1])
        return start + timedelta(days=(weekday - start.weekday()) % 7)
    if rule.startswith("every:"):
        step = int(rule.split(":")[1])
        d = last
        while d < start:
            d += timedelta(days=step)
        return d
    day, shift, every = parse_month_rule(rule)
    # phase: months after the last one seen, in steps of `every`
    y, m = last.year, last.month
    for k in range(0, 400):
        ny, nm = _month_add(y, m, every * k)
        nominal = nominal_date(ny, nm, day)
        if business_day(nominal, shift, day) >= start:
            return nominal
    raise ValueError(rule)


def _shifted(rule: str, nominal: date) -> date:
    if rule.startswith("month_day:"):
        day, shift, _ = parse_month_rule(rule)
        return business_day(nominal, shift, day)
    return nominal


def recurrence_for(rule: str) -> str:
    """The `ScheduledItem.recurrence` a rule becomes."""
    if rule.startswith("weekday:"):
        return "weekly"
    if rule == "every:14":
        return "biweekly"
    return rule  # month_day:..., every:<days>


# ------------------------------------------------------------- no double counting
def drop_duplicates(events: list[tuple[date, float, str, bool]]) -> list[tuple[date, float, str]]:
    """events: (date, amount, label, detected). A one-off the owner told us about (a quarterly
    flour order, an insurer's claim) that lands within 10 days of a detected occurrence of the
    same sign and a similar amount (within 40%: an insurer's payments vary a lot) replaces it:
    it is the same money."""
    detected = [e for e in events if e[3]]
    known = [e for e in events if not e[3]]
    removed: set[int] = set()
    for when, amount, *_rest in known:
        best, best_gap = None, None
        for i, (d_when, d_amount, *_rest) in enumerate(detected):
            if i in removed or (d_amount > 0) != (amount > 0):
                continue
            gap = abs((d_when - when).days)
            if (
                gap <= 10
                and abs(d_amount - amount) <= 0.4 * abs(amount)
                and (best_gap is None or gap < best_gap)
            ):
                best, best_gap = i, gap
        if best is not None:
            removed.add(best)
    kept = [e for i, e in enumerate(detected) if i not in removed] + known
    # (date, amount, label) plus whatever the caller added after the detected flag
    return sorted(((e[0], e[1], e[2], *e[4:]) for e in kept), key=lambda e: (e[0], e[1], e[2]))


ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 21: "21st", 22: "22nd", 23: "23rd", 31: "31st"}


def describe(recurrence: str | None, due: date) -> str:
    """How often, in plain words: 'weekly (Fridays)', 'monthly on the 15th', 'quarterly on the 15th'."""
    if not recurrence:
        return "once"
    if recurrence == "weekly":
        return f"weekly ({WEEKDAY_NAMES[due.weekday()]}s)"
    if recurrence == "biweekly":
        return f"every two weeks ({WEEKDAY_NAMES[due.weekday()]}s)"
    if recurrence == "monthly":
        return f"monthly on the {ORDINAL.get(due.day, f'{due.day}th')}"
    if recurrence.startswith("every:"):
        return f"about every {recurrence.split(':')[1]} days"
    if recurrence.startswith("month_day:"):
        day, _shift, every = parse_month_rule(recurrence)
        when = (
            "on the last business day" if day == "last_bd"
            else "on the last day" if day == "last"
            else f"on the {ORDINAL.get(int(day), f'{day}th')}"
        )  # fmt: skip
        how_often = {1: "monthly"}.get(every) or EVERY_N_MONTHS.get(every, f"every {every} months")
        return f"{how_often} {when}"
    return recurrence
