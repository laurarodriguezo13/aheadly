"""Actions for a shortfall alert (roadmap 3.2): code works out what could help, names the real
payment, and measures each one with the same what-if the owner can run.

Candidates:
- move_payment: a payment in the tight week that comes only once in the forecast's horizon (a
  one-off, or a quarterly or yearly bill) moved 1, 2 or 3 weeks later: the smallest move that
  helps most. Weekly or monthly payments are never offered: moving one would move them all.
- collect_early: the biggest money coming in once after cash first drops below the line, asked
  for the day before.
Only candidates that raise the lowest balance are kept, best first (status, then lowest balance).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from aheadly.ai import templates
from aheadly.ai.forecast_engine import expand_scheduled_items
from aheadly.domain import ScenarioResult, ScheduledItem, chance_pct

RISK_ORDER = {"safe": 0, "watch": 1, "act_now": 2}
MAX_ACTIONS = 3
MOVE_WEEKS = (1, 2, 3)

Evaluate = Callable[[list[dict]], ScenarioResult]


def _once(items: list[ScheduledItem], start: date, end: date) -> dict[str, tuple[ScheduledItem, date]]:
    """Active payments that land exactly once in the horizon, with that day."""
    found = {}
    for item in items:
        if not item.active or item.paused:
            continue
        events = expand_scheduled_items([item], start, end)
        if len(events) == 1:
            found[item.label] = (item, events[0][0])
    return found


def impact(result: ScenarioResult) -> dict:
    base, scen, line = result.baseline, result.scenario, result.low_cash_line
    return {
        "lowest_before": round(base.lowest.balance_p50),
        "lowest_after": round(scen.lowest.balance_p50),
        "risk_before": base.risk_level(line),
        "risk_after": scen.risk_level(line),
        "chance_before": chance_pct(base.chance_below(line)),
        "chance_after": chance_pct(scen.chance_below(line)),
    }


def _rank(found: dict) -> tuple:
    return (RISK_ORDER[found["impact"]["risk_after"]], -found["impact"]["lowest_after"])


def build(facts: dict, items: list[ScheduledItem], today: date, end: date, evaluate: Evaluate) -> list[dict]:
    once = _once(items, today, end)
    first_below = date.fromisoformat(facts["first_below_line_date"])
    found: list[dict] = []

    for outflow in facts["top_outflows"]:
        item, when = once.get(outflow["label"], (None, None))
        if item is None or item.amount >= 0:
            continue
        options = []
        for weeks in MOVE_WEEKS:
            new = when + timedelta(days=7 * weeks)
            if new > end:
                break
            adjustment = {"type": "move_item", "label": item.label, "new_date": new.isoformat()}
            options.append({"adjustment": adjustment, "impact": impact(evaluate([adjustment]))})
        if options:  # smallest move among the best ones (min keeps the first of equal keys)
            best = min(options, key=_rank)
            found.append({"kind": "move_payment", "item": item, "when": when, **best})

    later = [(i, d) for i, d in once.values() if i.amount > 0 and first_below < d <= end]
    for item, when in sorted(later, key=lambda pair: -pair[0].amount)[:1]:
        new = max(today, first_below - timedelta(days=1))
        adjustment = {"type": "collect_early", "label": item.label, "new_date": new.isoformat()}
        found.append(
            {
                "kind": "collect_early",
                "item": item,
                "when": when,
                "adjustment": adjustment,
                "impact": impact(evaluate([adjustment])),
            }
        )

    helpful = [f for f in found if f["impact"]["lowest_after"] > f["impact"]["lowest_before"]]
    actions = []
    for f in sorted(helpful, key=_rank)[:MAX_ACTIONS]:
        words = templates.action_words(
            f["kind"],
            f["item"].label,
            abs(f["item"].amount),
            f["when"].isoformat(),
            f["adjustment"]["new_date"],
        )
        actions.append(
            {
                **words,
                "kind": f["kind"],
                "adjustment": f["adjustment"],
                "impact": f["impact"],
                "when": f["when"].isoformat(),
                "amount": round(abs(f["item"].amount)),
            }
        )
    return actions


def message_facts(action: dict, business_name: str, owner_name: str) -> dict:
    """What a drafted message may say: nothing beyond the action itself."""
    return {
        "kind": action["kind"],
        "payee": action["adjustment"]["label"],
        "amount": action["amount"],
        "date": action["when"],
        "new_date": action["adjustment"]["new_date"],
        "business": business_name,
        "owner": owner_name or "",
    }
