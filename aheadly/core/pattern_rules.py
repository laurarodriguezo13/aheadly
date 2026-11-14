"""Things we noticed (roadmap 4.1): patterns in the statement worth knowing even when cash is fine.

Deterministic, like alert_rules.py: each rule looks at the business's own lines and returns facts
(numbers computed here) or nothing. The words come later (4.2); the guardrail checks every number.
Thresholds were set on the six test businesses' stories and answer keys (DECISIONS #43), and each
rule respects what the owner told us: a month they call busy or slow is never compared as if it
were a normal one.

Every rule reads `Lines`: the statement lines without moves between the owner's own accounts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from aheadly.ai.categorizer import match_key

# cost categories worth naming when they grow ("other" is unknown and "taxes" are lumpy on purpose)
NAMED_COSTS = ("suppliers", "rent", "utilities", "payroll", "bank_fees", "equipment")
# not a cost of running the business: the owner's pay, taxes, loans and card payments
NOT_COSTS = ("owner_pay", "taxes", "loan", "card_payment", "transfer_internal")
# money in that isn't one customer: card machines, cash deposits, delivery and payment platforms,
# interest; matched on whole words of the plain description
SETTLEMENT_WORDS = (
    "datafono",
    "redeban",
    "credibanco",
    "abono ventas",
    "consignacion",
    "efectivo",
    "deposito",
    "pasarela",
    "wompi",
    "payu",
    "rappi",
    "mercado pago",
    "nequi",
    "daviplata",
    "intereses",
    "interest",
    "card settlement",
    "merchant",
    "pos deposit",
    "cash deposit",
    "stripe",
    "square",
    "paypal",
)

THIN_CUSHION_WEEKS = 2.0
CREEP_SHARE, CREEP_DOLLARS = 0.15, 50.0
FASTER_POINTS, FASTER_MIN = 0.05, 0.05
SHRINK_SHARE = 0.05
OWNER_PAY_SHARE = 0.75
FEW_CUSTOMERS_SHARE = 0.25
LATER_DAYS, LATER_LAST = 33.0, 4
DUPLICATE_MIN = 20.0
UNUSUAL_TIMES_MEDIAN, UNUSUAL_SHARE = 3.0, 0.02
NEW_RECURRING_DAYS = 120
SLOWING_SHARE = 0.15


@dataclass
class Insight:
    type: str
    severity: str  # low | medium
    facts: dict = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)  # what could help; worded and tested in 4.2/4.3

    def as_dict(self) -> dict:
        return {"type": self.type, "severity": self.severity, "facts": self.facts, "actions": self.actions}


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def is_settlement(description: str) -> bool:
    plain = match_key(description)
    return any(_has(plain, w) for w in SETTLEMENT_WORDS)


def lines_frame(rows: list[tuple]) -> pd.DataFrame:
    """(id, date, amount, description, category, internal) → the lines the rules read."""
    df = pd.DataFrame(rows, columns=["id", "date", "amount", "description", "category", "internal"])
    df = df[df["internal"] == 0].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["key"] = df["description"].map(match_key)
    df["month"] = df["date"].dt.to_period("M")
    return df


def month_windows(today: date, months: int = 3) -> tuple[list, list]:
    """The last `months` complete months and the `months` before them."""
    last = pd.Period(today, "M") - 1
    recent = [last - i for i in range(months)][::-1]
    before = [recent[0] - i for i in range(1, months + 1)][::-1]
    return before, recent


def _seasonal(periods: list, seasons: set[int]) -> bool:
    return any(p.month in seasons for p in periods)


def _monthly(df: pd.DataFrame, periods: list) -> pd.Series:
    return df.groupby("month")["amount"].sum().reindex(periods, fill_value=0.0)


def _costs(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["amount"] < 0) & (~df["category"].isin(NOT_COSTS))]


def _sales(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["amount"] > 0) & (df["category"] == "sales")]


def _money_in(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["amount"] > 0) & (df["category"] != "loan")]


# ------------------------------------------------------------------------------ the rules
def thin_cushion(df: pd.DataFrame, today: date, balance: float) -> Insight | None:
    """Cash covers less than two weeks of what normally goes out (last 12 weeks)."""
    recent = df[(df["date"] > pd.Timestamp(today - timedelta(weeks=12))) & (df["amount"] < 0)]
    weekly_out = -recent["amount"].sum() / 12
    if weekly_out <= 0:
        return None
    weeks = balance / weekly_out
    if weeks >= THIN_CUSHION_WEEKS:
        return None
    return Insight(
        "thin_cushion",
        "medium",
        {
            "current_balance": round(balance),
            "weekly_money_out": round(weekly_out),
            "weeks_covered": round(weeks, 1),
        },
        ["build_buffer", "lower_owner_pay_for_a_while"],
    )


def cost_creeping_up(df: pd.DataFrame, today: date, seasons: set[int]) -> list[Insight]:
    """A named cost category up more than 15% and $50 a month, last 3 months against the 3 before."""
    before, recent = month_windows(today)
    if _seasonal(before + recent, seasons):
        return []
    costs = _costs(df)
    found = []
    for category in NAMED_COSTS:
        monthly = -_monthly(costs[costs["category"] == category], before + recent)
        was, now = monthly[before].mean(), monthly[recent].mean()
        if was > 0 and now > was * (1 + CREEP_SHARE) and now - was > CREEP_DOLLARS:
            found.append(
                Insight(
                    "cost_creeping_up",
                    "medium",
                    {
                        "category": category,
                        "monthly_before": round(was),
                        "monthly_now": round(now),
                        "change_pct": round((now / was - 1) * 100),
                    },
                    ["compare_suppliers", "raise_prices_to_cover"],
                )
            )
    return found


def costs_faster_than_sales(df: pd.DataFrame, today: date, seasons: set[int]) -> Insight | None:
    before, recent = month_windows(today)
    if _seasonal(before + recent, seasons):
        return None
    costs = -_monthly(_costs(df), before + recent)
    sales = _monthly(_sales(df), before + recent)
    c_was, c_now, s_was, s_now = (
        costs[before].mean(),
        costs[recent].mean(),
        sales[before].mean(),
        sales[recent].mean(),
    )
    if c_was <= 0 or s_was <= 0:
        return None
    cost_growth, sales_growth = c_now / c_was - 1, s_now / s_was - 1
    if cost_growth < FASTER_MIN or cost_growth - sales_growth < FASTER_POINTS:
        return None
    return Insight(
        "costs_faster_than_sales",
        "medium",
        {
            "costs_change_pct": round(cost_growth * 100),
            "sales_change_pct": round(sales_growth * 100),
            "monthly_costs_now": round(c_now),
            "monthly_sales_now": round(s_now),
        },
        ["review_prices", "renegotiate_with_suppliers"],
    )


def net_flow_shrinking(df: pd.DataFrame, today: date, seasons: set[int]) -> Insight | None:
    """What's left each month (money in minus out, loans aside) fell by more than 5% of monthly income."""
    before, recent = month_windows(today)
    if _seasonal(before + recent, seasons):
        return None
    flows = df[df["category"] != "loan"]
    net = _monthly(flows, before + recent)
    income = _monthly(_money_in(df), before + recent)
    was, now = net[before].mean(), net[recent].mean()
    if income.mean() <= 0 or was - now <= SHRINK_SHARE * income.mean():
        return None
    return Insight(
        "net_flow_shrinking",
        "medium",
        {"monthly_net_before": round(was), "monthly_net_now": round(now)},
        ["review_prices", "cut_a_cost"],
    )


def owner_pay_high(df: pd.DataFrame, today: date) -> Insight | None:
    """The owner takes more than 75% of what the business makes before paying them (last 6 months).
    Borrowing and repaying both stay out: a shop that borrows for its stock and repays from the
    season would otherwise look like it makes nothing."""
    before, recent = month_windows(today)
    months = before + recent
    window = df[df["month"].isin(months)]
    pay = -window[window["category"] == "owner_pay"]["amount"].sum() / len(months)
    if pay <= 0:
        return None
    flows = window[~window["category"].isin(("loan", "owner_pay"))]
    before_pay = flows["amount"].sum() / len(months)
    if before_pay > 0 and pay <= OWNER_PAY_SHARE * before_pay:
        return None
    return Insight(
        "owner_pay_high",
        "medium",
        {
            "monthly_owner_pay": round(pay),
            "monthly_left_before_pay": round(before_pay),
            "share_pct": round(pay / before_pay * 100) if before_pay > 0 else None,
        },
        ["lower_owner_pay_for_a_while"],
    )


def few_customers(df: pd.DataFrame, today: date) -> Insight | None:
    """One named customer brings a quarter or more of the money coming in (last 6 months)."""
    window = _money_in(df[df["date"] > pd.Timestamp(today - timedelta(days=183))])
    total = window["amount"].sum()
    named = window[~window["description"].map(is_settlement)]
    if total <= 0 or named.empty:
        return None
    by_key = named.groupby("key")["amount"].agg(["sum", "count"])
    by_key = by_key[by_key["count"] >= 3]
    if by_key.empty:
        return None
    key = by_key["sum"].idxmax()
    share = by_key.loc[key, "sum"] / total
    if share < FEW_CUSTOMERS_SHARE:
        return None
    label = named[named["key"] == key]["description"].iloc[-1]
    return Insight(
        "few_customers",
        "medium",
        {
            "customer": label,
            "share_pct": round(share * 100),
            "amount_6_months": round(by_key.loc[key, "sum"]),
        },
        ["find_another_customer", "ask_for_deposits"],
    )


def customers_paying_later(df: pd.DataFrame) -> list[Insight]:
    """A customer who pays about monthly now takes more than 33 days between payments (last four)."""
    found = []
    named = _money_in(df)
    named = named[~named["description"].map(is_settlement)]
    for key, group in named.groupby("key"):
        if len(group) < 6:
            continue
        gaps = group["date"].sort_values().diff().dropna().dt.days.tolist()
        typical = pd.Series(gaps).median()
        last = gaps[-LATER_LAST:]
        if not 25 <= typical <= 40 or sum(last) / len(last) <= LATER_DAYS or min(last) <= 32:
            continue
        earlier = gaps[:-LATER_LAST] or gaps
        found.append(
            Insight(
                "customers_paying_later",
                "medium",
                {
                    "customer": group["description"].iloc[-1],
                    "days_between_now": round(sum(last) / len(last)),
                    "days_between_before": round(pd.Series(earlier).median()),
                    "last_paid": group["date"].max().date().isoformat(),
                },
                ["send_reminder", "shorten_terms"],
            )
        )
    return found


def duplicate_charge(df: pd.DataFrame, today: date) -> list[Insight]:
    """The same payee charged the same amount twice on the same day (last 90 days)."""
    recent = df[(df["date"] > pd.Timestamp(today - timedelta(days=90))) & (df["amount"] <= -DUPLICATE_MIN)]
    doubled = recent[recent.duplicated(["date", "key", "amount"], keep="first")]
    return [
        Insight(
            "duplicate_charge",
            "medium",
            {"payee": row.description, "amount": round(-row.amount, 2), "date": row.date.date().isoformat()},
            ["ask_for_refund"],
        )
        for row in doubled.itertuples()
    ]


def unusual_charge(df: pd.DataFrame, today: date) -> list[Insight]:
    """A payee never seen before, charging at least 3× a usual payment and 2% of a month's spending
    (last 60 days)."""
    out = df[df["amount"] < 0]
    if out.empty:
        return []
    seen = out["key"].value_counts()
    monthly_out = -out[out["date"] > pd.Timestamp(today - timedelta(days=90))]["amount"].sum() / 3
    floor = max(UNUSUAL_TIMES_MEDIAN * out["amount"].abs().median(), UNUSUAL_SHARE * monthly_out)
    recent = out[(out["date"] > pd.Timestamp(today - timedelta(days=60))) & (out["key"].map(seen) == 1)]
    return [
        Insight(
            "unusual_charge",
            "low",
            {"payee": row.description, "amount": round(-row.amount, 2), "date": row.date.date().isoformat()},
            ["check_the_charge"],
        )
        for row in recent.itertuples()
        if -row.amount >= floor and row.category != "taxes"
    ]


def new_recurring_charge(found: list, first_dates: dict, today: date, history_start: date) -> list[Insight]:
    """A regular payment that started in the last 4 months (with months of history before it)."""
    out = []
    for item in found:
        if item.direction != "out" or item.internal or item.seasonal or item.occurrences < 3:
            continue
        first = first_dates.get(item.match_key)
        if first is None or first <= today - timedelta(days=NEW_RECURRING_DAYS):
            continue
        if (first - history_start).days < 90:
            continue
        out.append(
            Insight(
                "new_recurring_charge",
                "low",
                {
                    "payee": item.label,
                    "amount": round(-item.amount, 2),
                    "how_often": item.cadence,
                    "since": first.isoformat(),
                },
                ["cancel_if_not_needed"],
            )
        )
    return out


def sales_slowing(df: pd.DataFrame, today: date, seasons: set[int]) -> Insight | None:
    """Sales in the last 3 complete months more than 15% below the 3 before. Whole months, so a
    customer who pays monthly counts once in each; never across a month the owner calls busy or slow."""
    before, recent = month_windows(today)
    if _seasonal(before + recent, seasons):
        return None
    sales = _monthly(_sales(df), before + recent)
    was, now = sales[before].mean(), sales[recent].mean()
    if was <= 0 or now >= was * (1 - SLOWING_SHARE):
        return None
    return Insight(
        "sales_slowing",
        "medium",
        {
            "monthly_sales_before": round(was),
            "monthly_sales_now": round(now),
            "change_pct": round((now / was - 1) * 100),
        },
        ["promotion_on_slow_days"],
    )


def find(
    df: pd.DataFrame,
    today: date,
    balance: float,
    seasons: set[int],
    found_recurring: list,
    first_dates: dict,
) -> list[Insight]:
    """Every pattern rule, most important first."""
    if df.empty:
        return []
    history_start = df["date"].min().date()
    out: list[Insight] = []
    for single in (
        thin_cushion(df, today, balance),
        owner_pay_high(df, today),
        net_flow_shrinking(df, today, seasons),
        costs_faster_than_sales(df, today, seasons),
        few_customers(df, today),
        sales_slowing(df, today, seasons),
    ):
        if single:
            out.append(single)
    out += customers_paying_later(df)
    out += cost_creeping_up(df, today, seasons)
    out += duplicate_charge(df, today)
    out += unusual_charge(df, today)
    out += new_recurring_charge(found_recurring, first_dates, today, history_start)
    order = {"medium": 0, "low": 1}
    return sorted(out, key=lambda i: order[i.severity])
