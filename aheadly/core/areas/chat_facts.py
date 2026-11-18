"""What the chat's tools read: cash summary, forecast summary, payments, transactions, alerts."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from aheadly.ai import categorizer
from aheadly.core import alert_rules, insight_charts, pattern_rules
from aheadly.domain import (
    Business,
    ForecastResult,
    end_of_next_month,
)

from aheadly.core.areas.shared import (
    _from_statement,
)

logger = logging.getLogger(__name__)


class ChatFactsMixin:
    """Part of `AppCore` (issue 14): what the chat's tools read: cash summary, forecast summary, payments, transactions, alerts."""

    # ---------------------------------------------------- tool-facing queries
    def cash_summary(self) -> dict:
        business = self._business()
        totals = self.repo.flow_totals(business.id, self.today - timedelta(days=30))
        return {
            "current_balance": round(self.repo.current_balance(business.id)),
            "period_days": 30,
            "money_in_30d": round(totals["money_in"]),
            "money_out_30d": round(totals["money_out"]),
            "low_cash_line": round(business.low_cash_line),
            "currency": business.currency,
            **self._month_totals(),
        }

    def _month_totals(self) -> dict:
        """Money in and out per complete month (the Insights chart's numbers: loans and moves between
        the owner's own accounts left out) and this month so far, for "Will November be as good as
        October?" (found by the Gemini run: the chat only had the last 30 days)."""
        df = pattern_rules.lines_frame(self.repo.recurring_lines(self._business().id))
        rows = insight_charts.money_in_out(df, insight_charts.complete_months(df, self.today))
        current = pd.Period(self.today, "M")
        so_far = insight_charts.money_in_out(df, [current])[0] if not df.empty else None
        last_day = df[df["month"] == current]["date"].max() if not df.empty else None
        out = {
            "months": [
                {
                    "month": f"{r['month']:%b %Y}",
                    "money_in": r["money_in"],
                    "money_out": r["money_out"],
                    "left": r["net"],
                }
                for r in rows
            ],
            "months_note": "complete months; loans and moves between the owner's own accounts left out",
        }
        if so_far and pd.notna(last_day):
            out["this_month_so_far"] = {
                "month": current.strftime("%b %Y"),
                "through": f"{last_day:%b} {last_day.day}",
                "money_in": so_far["money_in"],
                "money_out": so_far["money_out"],
            }
        return out

    def forecast_summary(self, weeks: int = 8, until: str | None = None) -> dict:
        """`until` (ISO date) limits the answer to a window, e.g. the end of next month."""
        weeks = max(1, min(8, weeks))
        forecast = self._baseline_forecast()
        points = forecast.points[: weeks * 7]
        if until:
            end = date.fromisoformat(until)
            points = [p for p in forecast.points if p.date <= end] or points
        weekly = [
            {
                "week": i + 1,
                "date": p.date.isoformat(),
                "worst_case": round(p.balance_p10),
                "base_case": round(p.balance_p50),
                "best_case": round(p.balance_p90),
            }
            for i, p in enumerate(points)
            if (i + 1) % 7 == 0
        ]
        lowest = min(points, key=lambda p: p.balance_p50)
        line = self._business().low_cash_line
        window = ForecastResult(forecast.opening_balance, points, forecast.model)
        return {
            "weeks": weeks,
            "until": until,
            "weekly_balances": weekly,
            "lowest_point": {
                "date": lowest.date.isoformat(),
                "balance_base_case": round(lowest.balance_p50),
                "balance_worst_case": round(lowest.balance_p10),
                "weeks_ahead": alert_rules.weeks_until(self.today, lowest.date),
            },
            "lowest_worst_case": round(window.min_p10),
            "risk_level": window.risk_level(line),
            "chance_below_line_pct": alert_rules.chance_pct(
                forecast.chance_below(line, until=points[-1].date)
            ),
            "low_cash_line": round(line),
        }

    def biggest_upcoming_payment(self) -> str | None:
        """Label of the largest payment going out before the end of next month (for suggested questions)."""
        end = end_of_next_month(self.today)
        upcoming = [e for e in self._events(end - timedelta(days=1)) if e[1] < 0]
        return min(upcoming, key=lambda e: e[1])[2] if upcoming else None

    def planned_items(self) -> list[dict]:
        """What the forecast counts on beyond the statement: the owner's upcoming payments and income."""
        return [
            {
                "date": item.due_date.isoformat(),
                "description": item.label,
                "amount": round(item.amount, 2),
                "repeats": item.recurrence or "once",
            }
            for item in self.repo.list_scheduled_items(self._business().id)
            if not _from_statement(item)
        ]

    def upcoming_outflows(self, weeks: int = 8) -> list[dict]:
        end = self.today + timedelta(days=7 * max(1, min(8, weeks)))
        events = self._events(end)
        outflows = sorted((e for e in events if e[1] < 0), key=lambda e: e[1])
        return [
            {"label": label, "amount": round(-amount), "date": d.isoformat()}
            for d, amount, label in outflows[:8]
        ]

    def recent_transactions(
        self,
        category: str | None = None,
        since: str | None = None,
        limit: int = 10,
        search: str | None = None,
    ) -> list[dict]:
        """`search`: words from the payment's description, anywhere in the statement (the chat's "What is
        X?", found by the Gemini run: the newest 50 lines didn't reach it)."""
        since_date = date.fromisoformat(since) if since else None
        df = self.repo.list_transactions(
            self._business().id, since_date, category, max(1, min(50, limit)), (search or "").strip() or None
        )
        return [
            {"date": r.date, "description": r.description, "category": r.category, "amount": round(r.amount)}
            for r in df.itertuples()
        ]

    def alerts_as_dicts(self) -> list[dict]:
        return [
            {
                "title": a.title,
                "body": a.body,
                "severity": a.severity,
                "weeks_ahead": a.weeks_ahead,
                "facts": a.facts,
                # roadmap R.1: "How do I fix my alert?" gets the fixes, tested ones first
                "fixes": [
                    {
                        "label": action["label"],
                        "detail": action.get("detail", ""),
                        **({"tested": action["impact"]} if action.get("impact") else {}),
                    }
                    for action in sorted(a.actions, key=lambda action: not action.get("impact"))[:3]
                ],
            }
            for a in self.get_alerts()
        ]

    def latest_lines(self, limit: int = 20) -> pd.DataFrame:
        """The latest statement lines, for the Accounts page."""
        return self.repo.list_transactions(self._business().id, limit=limit)

    @staticmethod
    def answer_categories() -> list[str]:
        """Categories an owner can pick for a payee (not "other"; card payments are found by rule)."""
        return [c for c in categorizer.CATEGORIES if c not in ("other", "card_payment")]

    def scheduled_labels(self) -> list[str]:
        """Names of every payment the forecast counts on (the owner's and the ones found in the
        statement), so the chat can move or remove any of them."""
        return sorted({i.label for i in self.repo.list_scheduled_items(self._business().id)})

    def _prompt_context(self, business: Business) -> dict:
        labels = ", ".join(self.scheduled_labels())
        return {
            "business_name": business.name,
            "end_of_next_month": end_of_next_month(self.today).isoformat(),
            "owner_name": business.owner_name,
            "today": self.today.isoformat(),
            "currency": business.currency,
            "low_cash_line": round(business.low_cash_line),
            "scheduled_labels": labels or "none",
            # roadmap R.3c: the owner's own notes ("anything else we should know?"), as background
            "owner_notes": "; ".join(n["text"] for n in self.owner_notes()) or "nothing yet",
        }
