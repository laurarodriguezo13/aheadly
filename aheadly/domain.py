"""Domain objects shared by every layer.

Plain dataclasses, no behaviour that depends on Streamlit, SQLite or an LLM.
Sign convention everywhere: positive = money coming in, negative = money going out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

SCHEDULED_CATEGORIES = frozenset({"payroll", "rent", "planned_purchase", "bill"})


@dataclass
class Business:
    id: int
    name: str
    owner_name: str
    city: str
    currency: str = "USD"
    low_cash_line: float = 2000.0


@dataclass
class Transaction:
    date: date
    amount: float
    description: str
    category: str
    counterparty: str = ""
    source: str = "demo"
    external_id: str | None = None


@dataclass
class ScheduledItem:
    """Known future money in or out (a bill, payroll, rent, an invoice...)."""

    label: str
    amount: float
    due_date: date
    kind: str = "bill"
    recurrence: str | None = None  # None | weekly | biweekly | monthly
    id: int | None = None
    source: str = "demo"
    active: bool = True
    # where it came from and how sure we are (roadmap 1.4; used by detection and the forecast page)
    status: str = "user"  # detected (found in the statement) | confirmed (by the owner) | user (added)
    certainty: str = "confirmed"  # confirmed | maybe
    likelihood: float = 1.0  # for a maybe item: the chance it happens
    category: str | None = None
    match_key: str | None = None  # normalized payee, links it to the transactions it explains
    end_date: date | None = None
    user_edited: bool = False  # the owner changed it: detection never overwrites it again
    paused: bool = False
    # the date it was first planned for; moving it keeps this, so a payment the owner told us about
    # still stands in for the statement's copy of it after a move (review after Phase 3)
    first_due: date | None = None
    # how much it moved in the past (roadmap 2.8, worked out at forecast time, not stored): the
    # amount's spread as a share of it, and how many days early or late it usually comes
    spread: float = 0.0
    jitter_days: int = 0


@dataclass
class ForecastPoint:
    date: date
    balance_p10: float
    balance_p50: float
    balance_p90: float
    net_flow_p50: float


@dataclass
class ForecastResult:
    """Output of the Forecast Engine for one business and one set of scheduled items."""

    opening_balance: float
    points: list[ForecastPoint]
    model: str
    scheduled: list[tuple[date, float, str]] = field(default_factory=list)
    run_id: int | None = None
    # every path's balance day by day (n_paths × days); kept for this run only, never saved (roadmap 3.1)
    balance_paths: Any = field(default=None, repr=False, compare=False)
    # the chance saved with a stored run, for the low cash line at the time (paths aren't saved)
    saved_chance: float | None = None

    def chance_below(self, line: float, until: date | None = None) -> float | None:
        """Share of paths whose balance goes below `line` on at least one day up to `until` (default:
        the whole horizon); today's balance counts too. None when neither paths nor a saved chance exist."""
        if self.balance_paths is None:
            return self.saved_chance if until is None else None
        days = len(self.points) if until is None else sum(1 for p in self.points if p.date <= until)
        if self.opening_balance < line:
            return 1.0
        if days == 0:
            return 0.0
        dips = (self.balance_paths[:, :days] < line).any(axis=1)
        return float(dips.mean())

    @property
    def lowest(self) -> ForecastPoint:
        return min(self.points, key=lambda p: p.balance_p50)

    @property
    def min_p10(self) -> float:
        return min(p.balance_p10 for p in self.points)

    @property
    def min_p90(self) -> float:
        return min(p.balance_p90 for p in self.points)

    @property
    def horizon_end(self) -> date:
        return self.points[-1].date

    def lowest_with_today(self) -> tuple[float, date | None]:
        """Lowest base-case balance, counting today's balance too (date None = today is the lowest)."""
        low = self.lowest
        if self.opening_balance <= low.balance_p50:
            return self.opening_balance, None
        return low.balance_p50, low.date

    def risk_level(self, low_cash_line: float) -> str:
        """act_now: the base case drops below the line; watch: only the worst case does; safe: neither."""
        if self.lowest.balance_p50 < low_cash_line:
            return "act_now"
        if self.min_p10 < low_cash_line:
            return "watch"
        return "safe"

    def top_outflows(self, until: date, limit: int = 3, window_days: int = 7) -> list[dict[str, Any]]:
        """Largest scheduled outflows in the week ending on `until` (what the alert explains)."""
        start = until - timedelta(days=window_days - 1)
        window = [s for s in self.scheduled if s[1] < 0 and start <= s[0] <= until]
        window.sort(key=lambda s: s[1])
        return [
            {"label": label, "amount": round(-amount), "date": d.isoformat()}
            for d, amount, label in window[:limit]
        ]

    def inflows_before(self, until: date, limit: int = 3) -> list[dict[str, Any]]:
        window = [s for s in self.scheduled if s[1] > 0 and s[0] <= until]
        window.sort(key=lambda s: -s[1])
        return [
            {"label": label, "amount": round(amount), "date": d.isoformat()}
            for d, amount, label in window[:limit]
        ]


@dataclass
class Alert:
    id: int
    type: str  # shortfall | idle_cash
    severity: str  # low | medium | high
    weeks_ahead: int
    title: str
    body: str
    actions: list[dict[str, str]]
    facts: dict[str, Any]
    created_at: str
    read_at: str | None = None
    dismissed: bool = False
    resolved: bool = False


@dataclass
class Adjustment:
    """One change to test in a what-if scenario (see ai/scenarios.py)."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioResult:
    name: str
    adjustments: list[Adjustment]
    baseline: ForecastResult
    scenario: ForecastResult
    low_cash_line: float
    scenario_id: int | None = None

    @property
    def stays_above_line(self) -> bool:
        return self.scenario.lowest.balance_p50 >= self.low_cash_line

    def summary(self) -> dict[str, Any]:
        """Numbers only: this is what the LLM is allowed to talk about."""
        base, scen = self.baseline, self.scenario
        return {
            "scenario_name": self.name,
            "low_cash_line": round(self.low_cash_line),
            "baseline": {
                "lowest_base_case": round(base.lowest.balance_p50),
                "lowest_date": base.lowest.date.isoformat(),
                "lowest_worst_case": round(base.min_p10),
                "lowest_best_case": round(base.min_p90),
                "chance_below_line_pct": chance_pct(base.chance_below(self.low_cash_line)),
            },
            "scenario": {
                "lowest_base_case": round(scen.lowest.balance_p50),
                "lowest_date": scen.lowest.date.isoformat(),
                "lowest_worst_case": round(scen.min_p10),
                "lowest_best_case": round(scen.min_p90),
                "chance_below_line_pct": chance_pct(scen.chance_below(self.low_cash_line)),
            },
            "adjustments": [
                {
                    "type": a.type,
                    **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in a.params.items()},
                }
                for a in self.adjustments
            ],
            "change_in_lowest_base_case": round(scen.lowest.balance_p50 - base.lowest.balance_p50),
            "stays_above_low_cash_line": self.stays_above_line,
            "risk_level": self.scenario.risk_level(self.low_cash_line),
        }


@dataclass
class ChatAnswer:
    text: str
    tool_names: list[str] = field(default_factory=list)
    scenario: ScenarioResult | None = None
    used_fallback: bool = False
    proposals: list = field(default_factory=list)  # plan items to confirm (roadmap 2.4), never saved yet


def chance_pct(chance: float | None) -> int | None:
    """0.6421 → 64. 0 only when no path dips and 100 only when every path does (0.3% → 1, 99.8% → 99),
    so "none" and "every" in the words are always true (roadmap 3.1)."""
    if chance is None:
        return None
    pct = round(100 * chance)
    if 0 < chance and pct == 0:
        return 1
    if chance < 1 and pct == 100:
        return 99
    return pct


def end_of_next_month(today: date) -> date:
    """What 'next month' means for a payment date: the last day of the following month."""
    first_of_next = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    return (first_of_next + timedelta(days=32)).replace(day=1) - timedelta(days=1)
