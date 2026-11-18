"""Constants and small helpers the App Core areas share."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from aheadly.domain import Alert, Business, ForecastResult, ScheduledItem


@dataclass
class AppStatus:
    business: Business | None
    connected: bool
    accounts: list[dict]
    last_run_at: datetime | None
    llm_provider: str
    llm_model: str
    forecast_model: str


@dataclass
class DailyRunSummary:
    ran: bool
    alerts_raised: int = 0
    alerts_updated: int = 0
    alerts_resolved: int = 0
    forecast: ForecastResult | None = None


@dataclass
class Dashboard:
    business: Business
    balance: float
    forecast: ForecastResult | None
    history: pd.DataFrame
    alerts: list[Alert]
    next_payment: tuple[date, float, str] | None
    open_alerts: int = 0
    scheduled: list = field(default_factory=list)
    lowest_weeks: int | None = None  # weeks to the lowest day (None: it's today)
    chance_pct: int | None = None  # chance of dipping below the line, a whole percent (3.1)


# lines a what-if added (and, once saved, the plan lines they became) are never "the same money" as a
# payment found in the statement: a surprise bill the size of the rent must not replace the rent (3.5)
NEVER_PAIRED = ("scenario", "plan")


# what an insight's action changes, for the owner's "Not for me" rules (roadmap R.3)
INSIGHT_ACTION_KINDS = {
    "lower_owner_pay_for_a_while": "owner_pay",
    "review_prices": "price",
    "raise_prices_to_cover": "price",
    "cancel_if_not_needed": "cancel",
}


DECLINE_REASONS = ("wont_agree", "cant_lower_pay", "cant_raise_prices", "already_done", "other", "told_us")


CARD_PAYMENT = re.compile(r"\b(tarjeta|visa|mastercard|master card|amex|credit card|card payment|tc)\b")


def _agreeing(change: float | None, busy: bool) -> float:
    """The statement's measure of a month, used only when it agrees with the owner: a month they
    call busy that last time came in below normal changes nothing (they can type their own)."""
    if change is None or (change > 0) != busy or change == 0:
        return 0.0
    return change


def _from_statement(item: ScheduledItem) -> bool:
    """Found in the bank statement (still true once the owner confirms or edits it)."""
    return item.status == "detected" or bool(item.match_key)


def _already_planned(item: ScheduledItem, planned: list[ScheduledItem]) -> bool:
    """The same payment is already in the plan (typed by the owner or from another file)."""
    return any(
        (p.amount > 0) == (item.amount > 0)
        and abs(p.amount - item.amount) <= 0.01 * abs(item.amount)
        and abs((p.due_date - item.due_date).days) <= 3
        for p in planned
    )


def _kind(category: str | None, amount: float) -> str:
    """A scheduled item's kind from the category of the lines it comes from."""
    if category in ("payroll", "rent"):
        return category
    return "receivable" if amount > 0 else "bill"


def _adjustment_dict(adjustment) -> dict:
    params = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in adjustment.params.items()}
    return {"type": adjustment.type, **params}
