"""The Insights page's charts (roadmap 4.3): numbers per month from the statement lines.

Each function reads `pattern_rules.lines_frame` (the statement without moves between the owner's
own accounts) and returns plain numbers for the chart and the facts its summary is written from
(roadmap 4.2). No "sales by weekday": a bank statement shows the day the money arrived, and card
machines and apps pay out a day or more after the sale (Monday carries the weekend), so it would
name the wrong busy day (DECISIONS #45). Borrowing and repaying are left out of money in and out, as in the pattern rules: a
loan is neither a sale nor a cost of running the business.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from aheadly.ai.templates import CATEGORY_WORDS, payee_name
from aheadly.core.pattern_rules import is_settlement

MONTHS = 12
TOP_CATEGORIES = 5
NOT_SPENDING = ("loan", "card_payment", "transfer_internal")
SOURCE_MONTHS = 6
TOP_SOURCES = 4
GROWTH_SHARE = 0.15  # a cost that grew less than this isn't "the one that grew most" (as in 4.1)
NO_GROWTH = ("Taxes", "Your own pay")  # lumpy on purpose, or the owner's choice: never "grew the most"
CUSHION_WEEKS = 2.0
CARD_AND_CASH = "Card, cash and app sales"
OTHER_IN = "Other money in"
OTHER_COSTS = "Everything else"


def complete_months(df: pd.DataFrame, today: date, n: int = MONTHS) -> list[pd.Period]:
    """The last `n` complete months the statement covers from their first day."""
    if df.empty:
        return []
    last = pd.Period(today, "M") - 1
    first = pd.Period(df["date"].min(), "M")
    if df["date"].min().day != 1:
        first += 1
    return [p for p in (last - i for i in range(n - 1, -1, -1)) if p >= first]


def month_name(period: pd.Period) -> str:
    return period.strftime("%b %Y")


def _flows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["category"] != "loan"]


# ------------------------------------------------------------------- money in vs out by month
def money_in_out(df: pd.DataFrame, months: list[pd.Period]) -> list[dict]:
    flows = _flows(df[df["month"].isin(months)])
    rows = []
    for m in months:
        month = flows[flows["month"] == m]["amount"]
        money_in, money_out = month[month > 0].sum(), -month[month < 0].sum()
        rows.append(
            {
                "month": m.start_time.date(),
                "money_in": round(money_in),
                "money_out": round(money_out),
                "net": round(money_in - money_out),
            }
        )
    return rows


def money_in_out_facts(rows: list[dict]) -> dict | None:
    if len(rows) < 2:
        return None
    best = max(rows, key=lambda r: r["net"])
    worst = min(rows, key=lambda r: r["net"])
    return {
        "chart": "money_in_out",
        "months": len(rows),
        "average_in": round(sum(r["money_in"] for r in rows) / len(rows)),
        "average_out": round(sum(r["money_out"] for r in rows) / len(rows)),
        "months_more_out": sum(1 for r in rows if r["net"] < 0),
        "best_month": {"month": f"{best['month']:%b %Y}", "net": best["net"]},
        "worst_month": {"month": f"{worst['month']:%b %Y}", "net": worst["net"]},
    }


# ------------------------------------------------------------------- spending by category
def _category_name(category: str) -> str:
    word = CATEGORY_WORDS.get(category, category.replace("_", " "))
    return word[:1].upper() + word[1:]


def spending_by_category(df: pd.DataFrame, months: list[pd.Period]) -> tuple[list[str], list[dict]]:
    """The biggest cost categories (named) and the rest, per month: (names, rows)."""
    costs = df[(df["amount"] < 0) & (~df["category"].isin(NOT_SPENDING)) & (df["month"].isin(months))]
    if costs.empty:
        return [], []
    totals = -costs.groupby("category")["amount"].sum()
    top = [c for c in totals.sort_values(ascending=False).index if c != "other"][:TOP_CATEGORIES]
    rows = []
    for m in months:
        month = costs[costs["month"] == m]
        row = {"month": m.start_time.date()}
        for c in top:
            row[_category_name(c)] = round(-month[month["category"] == c]["amount"].sum())
        row[OTHER_COSTS] = round(-month[~month["category"].isin(top)]["amount"].sum())
        rows.append(row)
    return [_category_name(c) for c in top] + [OTHER_COSTS], rows


def spending_facts(names: list[str], rows: list[dict]) -> dict | None:
    named = [n for n in names if n != OTHER_COSTS]
    if len(rows) < 2 or not named:
        return None
    total = sum(sum(r[n] for n in names) for r in rows)
    monthly = {n: sum(r[n] for r in rows) / len(rows) for n in named}
    biggest = max(named, key=lambda n: monthly[n])
    facts = {
        "chart": "spending",
        "months": len(rows),
        "biggest": {
            "category": biggest,
            "monthly": round(monthly[biggest]),
            "share_pct": round(monthly[biggest] * len(rows) / total * 100) if total else 0,
        },
        "grew_most": None,
    }
    if len(rows) >= 6:
        growth = []
        for n in named:
            if n in NO_GROWTH:
                continue
            before = sum(r[n] for r in rows[-6:-3]) / 3
            now = sum(r[n] for r in rows[-3:]) / 3
            if before > 0 and now > before * (1 + GROWTH_SHARE):
                growth.append((now / before, n, before, now))
        if growth:
            _, n, before, now = max(growth)
            facts["grew_most"] = {"category": n, "monthly_before": round(before), "monthly_now": round(now)}
    return facts


# ------------------------------------------------------------------- cash cushion
def cushion(df: pd.DataFrame, balance: float, today: date, months: list[pd.Period]) -> list[dict]:
    """Weeks of normal spending the cash covers at each month's end, and today."""
    out = df[df["amount"] < 0]
    points = [(m.end_time.date(), month_name(m)) for m in months] + [(today - timedelta(days=1), "Today")]
    rows = []
    for end, label in points:
        stamp = pd.Timestamp(end)
        cash = balance - df[df["date"] > stamp]["amount"].sum()
        window = out[(out["date"] > stamp - pd.Timedelta(weeks=12)) & (out["date"] <= stamp)]
        weekly = -window["amount"].sum() / 12
        if weekly > 0 and window["date"].min() <= stamp - pd.Timedelta(weeks=10):
            rows.append({"date": end, "label": label, "cash": round(cash), "weeks": round(cash / weekly, 1)})
    return rows


def cushion_facts(rows: list[dict]) -> dict | None:
    if len(rows) < 3:
        return None
    months = [r for r in rows if r["label"] != "Today"]
    low, high = min(months, key=lambda r: r["weeks"]), max(months, key=lambda r: r["weeks"])
    return {
        "chart": "cushion",
        "weeks_now": rows[-1]["weeks"],
        "lowest": {"month": low["label"], "weeks": low["weeks"]},
        "highest": {"month": high["label"], "weeks": high["weeks"]},
        "target_weeks": CUSHION_WEEKS,
    }


# ------------------------------------------------------------------- where income comes from
def income_sources(df: pd.DataFrame, today: date) -> list[dict]:
    """Money in over the last 6 months: the biggest named customers, card/cash/app sales, the rest."""
    window = df[(df["date"] > pd.Timestamp(today - timedelta(days=183))) & (df["amount"] > 0)]
    window = window[window["category"] != "loan"]
    total = window["amount"].sum()
    if total <= 0:
        return []
    settled = window["description"].map(is_settlement)
    named = window[~settled]
    by_key = named.groupby("key")["amount"].agg(["sum", "count"])
    by_key = by_key[by_key["count"] >= 3].sort_values("sum", ascending=False).head(TOP_SOURCES)
    rows = []
    for key, row in by_key.iterrows():
        label = payee_name(named[named["key"] == key]["description"].iloc[-1])
        rows.append({"source": label, "amount": round(row["sum"])})
    card = window[settled]["amount"].sum()
    if card > 0:
        rows.append({"source": CARD_AND_CASH, "amount": round(card)})
    rest = total - sum(r["amount"] for r in rows)
    if rest > 0.5:
        rows.append({"source": OTHER_IN, "amount": round(rest)})
    rows.sort(key=lambda r: -r["amount"])
    for r in rows:
        r["share_pct"] = round(r["amount"] / total * 100)
    return rows


def income_facts(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    top = rows[0]
    return {
        "chart": "income_sources",
        "months": SOURCE_MONTHS,
        "total": sum(r["amount"] for r in rows),
        "top": {**top, "many_customers": top["source"] == CARD_AND_CASH},
    }
