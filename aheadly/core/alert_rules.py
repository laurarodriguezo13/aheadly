"""Alert rules: deterministic, no LLM (the LLM only writes the words).

shortfall : any day where the base-case balance drops below the low cash line.
idle_cash : even the worst case stays above three months of outflows all horizon.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from aheadly.domain import Alert, Business, ForecastResult, chance_pct

POSSIBLE_ACTIONS = [
    "collect_receivables_early",
    "adjust_inventory_orders",
    "negotiate_payment_terms",
    "delay_planned_purchase",
]
DUPLICATE_WINDOW_DAYS = 3


@dataclass
class AlertFacts:
    """The numbers an alert is built from; this is all the LLM may use."""

    type: str
    severity: str
    weeks_ahead: int
    risk_date: date
    facts: dict = field(default_factory=dict)


def severity_for(weeks_ahead: int, lowest_balance: float) -> str:
    if weeks_ahead <= 2 or lowest_balance < 0:
        return "high"
    if weeks_ahead <= 5:
        return "medium"
    return "low"


def weeks_until(today: date, target: date) -> int:
    """Whole weeks to a date, rounded to the nearest week (never less than one)."""
    return max(1, round((target - today).days / 7))


def detect_shortfall(forecast: ForecastResult, business: Business, today: date) -> AlertFacts | None:
    below = [p for p in forecast.points if p.balance_p50 < business.low_cash_line]
    if not below:
        return None
    lowest = forecast.lowest
    first_cross = below[0]
    weeks_ahead = weeks_until(today, lowest.date)
    facts = {
        "type": "shortfall",
        "current_balance": round(forecast.opening_balance),
        "low_cash_line": round(business.low_cash_line),
        "lowest_balance": round(lowest.balance_p50),
        "lowest_date": lowest.date.isoformat(),
        "first_below_line_date": first_cross.date.isoformat(),
        "weeks_ahead": weeks_ahead,
        "chance_below_line_pct": chance_pct(forecast.chance_below(business.low_cash_line)),
        "top_outflows": forecast.top_outflows(lowest.date),
        "expected_inflows_before": forecast.inflows_before(lowest.date),
        "possible_actions": POSSIBLE_ACTIONS,
    }
    return AlertFacts(
        "shortfall", severity_for(weeks_ahead, lowest.balance_p50), weeks_ahead, lowest.date, facts
    )


def detect_idle_cash(
    forecast: ForecastResult, business: Business, avg_monthly_outflow: float, today: date
) -> AlertFacts | None:
    buffer = 3 * avg_monthly_outflow
    if avg_monthly_outflow <= 0 or forecast.min_p10 <= buffer:
        return None
    facts = {
        "type": "idle_cash",
        "current_balance": round(forecast.opening_balance),
        "lowest_worst_case": round(forecast.min_p10),
        "three_months_of_outflows": round(buffer),
        "horizon_weeks": math.ceil(len(forecast.points) / 7),
        "possible_actions": ["pay_supplier_early_for_discount", "buy_inventory_in_bulk"],
    }
    return AlertFacts("idle_cash", "low", facts["horizon_weeks"], forecast.horizon_end, facts)


def detect_alerts(
    forecast: ForecastResult, business: Business, avg_monthly_outflow: float, today: date
) -> list[AlertFacts]:
    candidates = [
        detect_shortfall(forecast, business, today),
        detect_idle_cash(forecast, business, avg_monthly_outflow, today),
    ]
    return [c for c in candidates if c is not None]


def find_duplicate(existing: list[Alert], new: AlertFacts) -> Alert | None:
    """An open alert of the same type with a risk date within ±3 days is updated, not duplicated."""
    for alert in existing:
        if alert.type != new.type:
            continue
        key = "lowest_date" if new.type == "shortfall" else None
        if key is None:
            return alert
        previous = date.fromisoformat(alert.facts.get(key, new.risk_date.isoformat()))
        if abs((previous - new.risk_date).days) <= DUPLICATE_WINDOW_DAYS:
            return alert
    return None
