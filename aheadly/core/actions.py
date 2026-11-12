"""Suggested fixes (roadmap 3.2 actions, 3.3 fixes): code works out what could help, names the
real payment, and measures each idea with the same what-if the owner can run.

Candidates (each a "family" with a few options; the smallest option that reaches the family's
best status is kept):
- move_payment: a payment that lands once in the horizon (a one-off, a quarterly or yearly bill),
  due between today and the low point, moved 1, 2 or 3 weeks later, to the day after the low point,
  or to the day after money that comes in once later. Weekly or monthly payments are never moved
  once: moving one would move them all.
- collect_early: the two biggest amounts coming in once after cash first drops below the line,
  asked for the day before.
- owner_pay: the owner's own pay (once the owner said which transfer it is) 25%, 50% or 100% lower
  for the next 8 weeks.
- price: prices about 5% or 10% higher, if customers keep buying as before.
Only ideas that help are kept. Order: status after the change, then how much it asks of the owner
(moving a date costs nothing, less pay or higher prices do), then the worst case. When no single
idea changes the status, pairs of the top five are tried too. At most three are shown.
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import combinations
from typing import Callable

from aheadly.ai import templates
from aheadly.ai.forecast_engine import expand_scheduled_items
from aheadly.domain import ForecastResult, ScenarioResult, ScheduledItem, chance_pct

RISK_ORDER = {"safe": 0, "watch": 1, "act_now": 2}
COST = {"move_payment": 0, "collect_early": 0, "owner_pay": 1, "price": 2}
MAX_ACTIONS = 3
PAIR_POOL = 5
MOVE_WEEKS = (1, 2, 3)
PAY_CUTS = (25, 50, 100)
PRICE_RISES = (5, 10)
MESSAGE_KINDS = ("move_payment", "collect_early")
# payments that aren't the owner's to move: wages, taxes, loan instalments and utility bills (late
# fees, legal dates, cut-offs). The owner's own pay has its own suggestion.
NEVER_MOVE = frozenset({"payroll", "taxes", "loan", "utilities", "bank_fees", "owner_pay"})
MIN_CHANCE_DROP = 5  # points
MIN_LIFT_SHARE = 0.10  # of the low cash line

Evaluate = Callable[[list[dict]], ScenarioResult]


def _once(items: list[ScheduledItem], start: date, end: date) -> list[tuple[ScheduledItem, date]]:
    """Active payments that land exactly once in the horizon, with that day."""
    found = []
    for item in items:
        if item.active and not item.paused:
            events = expand_scheduled_items([item], start, end)
            if len(events) == 1:
                found.append((item, events[0][0]))
    return found


def impact(result: ScenarioResult) -> dict:
    base, scen, line = result.baseline, result.scenario, result.low_cash_line
    return {
        "lowest_before": round(base.lowest.balance_p50),
        "lowest_after": round(scen.lowest.balance_p50),
        "worst_before": round(base.min_p10),
        "worst_after": round(scen.min_p10),
        "risk_before": base.risk_level(line),
        "risk_after": scen.risk_level(line),
        "chance_before": chance_pct(base.chance_below(line)),
        "chance_after": chance_pct(scen.chance_below(line)),
    }


def rank_key(action: dict) -> tuple:
    i = action["impact"]
    return (RISK_ORDER[i["risk_after"]], action["cost"], -i["worst_after"], -i["lowest_after"])


def _helps(i: dict, low_cash_line: float) -> bool:
    """Worth showing: the status gets better, the chance drops by 5 points or more, or the lowest
    balance rises by at least a tenth of the line (not a $20 nudge)."""
    if RISK_ORDER[i["risk_after"]] < RISK_ORDER[i["risk_before"]]:
        return True
    if (i["chance_before"] or 0) - (i["chance_after"] or 0) >= MIN_CHANCE_DROP:
        return True
    return i["lowest_after"] - i["lowest_before"] >= MIN_LIFT_SHARE * low_cash_line


def _weekday(d: date, back: bool = False) -> date:
    """Saturday or Sunday → Monday (or Friday when asking for money earlier)."""
    while d.weekday() >= 5:
        d += timedelta(days=-1 if back else 1)
    return d


def still_short(found: list[dict], low_cash_line: float) -> int | None:
    """How much the base case still misses the line after the best suggestion (None: it doesn't)."""
    if not found or found[0]["impact"]["risk_after"] != "act_now":
        return None
    return round(low_cash_line - found[0]["impact"]["lowest_after"])


def _families(baseline, line, items, today, end, weekly_sales) -> list[dict]:
    risk = baseline.risk_level(line)
    if risk == "act_now":
        below = [p for p in baseline.points if p.balance_p50 < line]
        low_date = baseline.lowest.date
    else:
        below = [p for p in baseline.points if p.balance_p10 < line]
        low_date = min(baseline.points, key=lambda p: p.balance_p10).date
    first_below = below[0].date
    once = _once(items, today, end)
    later_in = sorted(d for i, d in once if i.amount > 0 and low_date < d <= end)
    families = []

    for item, when in once:
        if item.amount < 0 and today <= when <= low_date and item.category not in NEVER_MOVE:
            dates = {when + timedelta(days=7 * w) for w in MOVE_WEEKS} | {low_date + timedelta(days=1)}
            dates = {_weekday(d) for d in dates | {d + timedelta(days=1) for d in later_in[:3]}}
            options = [
                ([{"type": "move_item", "label": item.label, "new_date": d.isoformat()}], (d - when).days)
                for d in sorted(dates)
                if when < d <= end
            ]
            if options:
                families.append({"kind": "move_payment", "item": item, "when": when, "options": options})

    coming = sorted(
        ((i, d) for i, d in once if i.amount > 0 and first_below < d <= end), key=lambda p: -p[0].amount
    )
    for item, when in coming[:2]:
        new = max(today, _weekday(first_below - timedelta(days=1), back=True))
        if new < when:
            adjustment = {"type": "collect_early", "label": item.label, "new_date": new.isoformat()}
            families.append(
                {
                    "kind": "collect_early",
                    "item": item,
                    "when": when,
                    "options": [([adjustment], (when - new).days)],
                }
            )

    for item in items:
        if (
            item.active
            and not item.paused
            and item.category == "owner_pay"
            and item.recurrence
            and item.amount < 0
        ):
            options = [
                (
                    [
                        {
                            "type": "recurring_change",
                            "label": item.label,
                            "amount_delta": round(-item.amount * pct / 100, 2),
                            "start_date": today.isoformat(),
                        }
                    ],
                    pct,
                )
                for pct in PAY_CUTS
            ]
            families.append({"kind": "owner_pay", "item": item, "when": None, "options": options})

    if weekly_sales > 0:
        options = [
            ([{"type": "revenue_change", "percent": pct, "start_date": today.isoformat()}], pct)
            for pct in PRICE_RISES
        ]
        families.append({"kind": "price", "item": None, "when": None, "options": options})
    return families


def _words(family: dict, adjustments: list[dict], size: int, weekly_sales: float) -> dict:
    kind, item = family["kind"], family["item"]
    if kind in MESSAGE_KINDS:
        return templates.action_words(
            kind,
            payee=item.label,
            amount=abs(item.amount),
            when=family["when"].isoformat(),
            new_when=adjustments[0]["new_date"],
        )
    if kind == "owner_pay":
        return templates.action_words(kind, payee=item.label, amount=abs(item.amount), pct=size)
    return templates.action_words(kind, pct=size, weekly=weekly_sales)


def build(
    baseline: ForecastResult,
    low_cash_line: float,
    items: list[ScheduledItem],
    today: date,
    end: date,
    evaluate: Evaluate,
    weekly_sales: float = 0.0,
) -> list[dict]:
    if baseline.risk_level(low_cash_line) == "safe":
        return []
    singles = []
    for family in _families(baseline, low_cash_line, items, today, end, weekly_sales):
        tried = [(adjs, size, impact(evaluate(adjs))) for adjs, size in family["options"]]
        best_risk = min(RISK_ORDER[i["risk_after"]] for _, _, i in tried)
        adjs, size, i = min(
            (t for t in tried if RISK_ORDER[t[2]["risk_after"]] == best_risk),
            key=lambda t: (t[1], -t[2]["worst_after"]),
        )
        if not _helps(i, low_cash_line):
            continue
        action = {
            **_words(family, adjs, size, weekly_sales),
            "kind": family["kind"],
            "cost": COST[family["kind"]],
            "adjustments": adjs,
            "impact": i,
        }
        if family["kind"] in MESSAGE_KINDS:
            action |= {"when": family["when"].isoformat(), "amount": round(abs(family["item"].amount))}
        singles.append(action)
    singles.sort(key=rank_key)

    found = list(singles)
    start_risk = RISK_ORDER[baseline.risk_level(low_cash_line)]
    if not singles or RISK_ORDER[singles[0]["impact"]["risk_after"]] == start_risk:
        best_single = RISK_ORDER[singles[0]["impact"]["risk_after"]] if singles else start_risk
        for a, b in combinations(singles[:PAIR_POOL], 2):
            if a["kind"] == b["kind"] and a["kind"] in ("owner_pay", "price"):
                continue
            adjs = a["adjustments"] + b["adjustments"]
            i = impact(evaluate(adjs))
            if RISK_ORDER[i["risk_after"]] < best_single:
                found.append(
                    {
                        **pair_words(a, b),
                        "kind": "pair",
                        "cost": a["cost"] + b["cost"] + 1,
                        "adjustments": adjs,
                        "impact": i,
                    }
                )
    found.sort(key=rank_key)
    return found[:MAX_ACTIONS]


def pair_words(a: dict, b: dict) -> dict:
    second = b["label"][0].lower() + b["label"][1:]
    return {
        "label": f"{a['label']} + {second}",
        "detail": f"{a.get('detail', '')} {b.get('detail', '')}".strip(),
        "how_to": [
            a["how_to"][0],
            b["how_to"][0],
            "If both work out, press Test this, then Save as my plan.",
        ],
    }


def message_facts(action: dict, business_name: str, owner_name: str) -> dict:
    """What a drafted message may say: nothing beyond the action itself."""
    adjustment = action["adjustments"][0]
    return {
        "kind": action["kind"],
        "payee": adjustment["label"],
        "amount": action["amount"],
        "date": action["when"],
        "new_date": adjustment["new_date"],
        "business": business_name,
        "owner": owner_name or "",
    }
