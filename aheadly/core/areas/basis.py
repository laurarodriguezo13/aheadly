"""Behind the forecast: what it counts on, changing it, how much to trust it, "just say it" (2.4, 2.6, 2.8)."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, timedelta

import pandas as pd

from aheadly.ai import confidence, plan_text, recurring
from aheadly.ai.plan_text import ProposedItem
from aheadly.ai.forecast_engine import (
    expand_scheduled_items,
    uncertain_income,
)
from aheadly.domain import (
    ScheduledItem,
)

logger = logging.getLogger(__name__)


class BasisMixin:
    """Part of `AppCore` (issue 14): behind the forecast: what it counts on, changing it, how much to trust it, "just say it" (2.4, 2.6, 2.8)."""

    # ------------------------------------------------------------ how much to trust it (roadmap 2.8)
    def forecast_confidence(self) -> dict:
        """High, medium or low, with the two biggest reasons (see aheadly/ai/confidence.py)."""
        business = self._business()
        profile = self.repo.get_profile(business.id)
        summary = self.repo.statement_summary(business.id)
        days = (
            (date.fromisoformat(summary["last"]) - date.fromisoformat(summary["first"])).days + 1
            if summary["first"]
            else 0
        )
        end = self.statement_end() or self.today
        recent = self.repo.flow_totals(business.id, end - timedelta(days=90))
        lines = self.repo.line_count(business.id, end - timedelta(days=90))
        unplaced = sum(
            p["count"] for p in self.repo.uncategorized_payees(business.id, end - timedelta(days=90))
        )
        checks = [
            confidence.history_check(days),
            confidence.unidentified_check(unplaced / lines if lines else 0.0),
            confidence.statement_check(int(profile.get("balance_breaks", 0))),
            confidence.backtest_check(self._backtest_error(business, recent)),
            confidence.answers_check(*self._questions_answered(profile)),
        ]
        return confidence.level(checks)

    def _questions_answered(self, profile: dict) -> tuple[int, int]:
        """(answered, asked): skipped questions count as asked, not answered."""
        done = profile.get("onboarding_done", [])
        skipped = set(profile.get("onboarding_skipped", []))
        left = profile.get("questions_left") or 0
        return len([q for q in done if q not in skipped]), len(done) + left

    def no_one_offs_planned(self) -> bool:
        """No one-off payment known in the forecast's window: the dashboard asks about big purchases."""
        end = self.today + timedelta(days=self.settings.horizon_days - 1)
        return not any(
            not i.recurrence and not i.paused and self.today <= i.due_date <= end
            for i in self.repo.list_scheduled_items(self._business().id)
        )

    def _backtest_error(self, business, recent: dict) -> float | None:
        """Forecast the last 4 weeks from the weeks before and compare (cached per history)."""
        history = self._model_history(business)
        if len(history) < 84:
            return None
        key = (business.id, len(history), round(float(history["net_flow"].sum()), 2))
        if key not in self._backtests:
            errors = self.engine.backtest(history)
            error = errors.get(type(self.engine._model).__name__, min(errors.values()))
            typical = (recent["money_in"] + recent["money_out"]) / 90
            self._backtests[key] = round(error / typical, 2) if typical else None
        return self._backtests[key]

    # ------------------------------------------------------------ the forecast's basis (roadmap 2.6)
    def forecast_basis(self) -> dict:
        """Everything the forecast counts on, in the order the "How we built your forecast" page
        shows it: where it starts, the normal rhythm, regular payments, one-offs, what it leaves out,
        and next month at a glance."""
        business = self._business()
        items = self.repo.list_scheduled_items(business.id)
        found = {r.match_key: r for r in self.detected_recurring()}
        summary = self.repo.statement_summary(business.id)
        regular = [self._basis_item(i, found) for i in items if i.recurrence]
        one_offs = [self._basis_item(i, found) for i in items if not i.recurrence]
        return {
            "start": {
                "balance": self.repo.current_balance(business.id),
                "statement_end": self.statement_end(),
                "today": self.today,
                "history_from": date.fromisoformat(summary["first"]) if summary["first"] else None,
                "transactions": summary["transactions"],
                "unidentified": summary["unidentified"],
                "accounts": len(self.repo.list_accounts(business.id)),
            },
            "rhythm": self._rhythm(business.id),
            "regular": sorted(regular, key=lambda r: (r["next"] or date.max, r["label"])),
            "one_offs": sorted(one_offs, key=lambda r: (r["due"], r["label"])),
            "suggestions": self._update_suggestions(items, found),
            "not_counted": self._not_counted(business.id, found),
            "next_month": self._next_month(),
        }

    def update_plan_item(self, item_id: int, **changes) -> dict:
        """The owner changes an item (amount, label, next date, end date, certain or maybe). From now
        on it's theirs: a later upload suggests changes but never overwrites them. Returns the effect."""
        item = self._own_item(item_id)
        if changes.get("certainty") not in (None, "confirmed", "maybe"):
            raise ValueError("certainty is confirmed or maybe")
        if "amount" in changes and changes["amount"] is not None:
            amount = abs(float(changes["amount"]))
            changes["amount"] = amount if item.amount > 0 else -amount
        changes = {k: v for k, v in changes.items() if v is not None or k == "end_date"}
        status = "confirmed" if item.status == "detected" else item.status
        if "amount" in changes:
            self._remember_edit(item_id)
        return self._change(item_id, user_edited=True, status=status, **changes)

    def _remember_edit(self, item_id: int) -> None:
        """Which statement the owner had when they set an amount: only a newer statement can suggest
        a different one (otherwise the page would argue with them right after they changed it)."""
        business = self._business()
        seen = dict(self.repo.get_profile(business.id).get("amount_set_with_statement", {}))
        end = self.statement_end()
        seen[str(item_id)] = end.isoformat() if end else None
        self.repo.save_profile(business.id, {"amount_set_with_statement": seen})

    def confirm_plan_item(self, item_id: int) -> None:
        """The owner says a payment found in the statement is right as it is."""
        self._own_item(item_id)
        self.repo.update_scheduled_item(item_id, status="confirmed", user_edited=True)

    def pause_plan_item(self, item_id: int, paused: bool = True) -> dict:
        self._own_item(item_id)
        return self._change(item_id, paused=paused, user_edited=True)

    def delete_plan_item(self, item_id: int) -> dict:
        """Removed from the forecast and kept switched off, so a later upload doesn't bring it back."""
        self._own_item(item_id)
        return self._change(item_id, active=False, user_edited=True)

    def _own_item(self, item_id: int) -> ScheduledItem:
        item = self.repo.scheduled_item(item_id)
        if item is None or item.id is None:
            raise ValueError("That payment isn't in your plan any more.")
        return item

    def _change(self, item_id: int, **fields) -> dict:
        """Apply a change and rerun the forecast; the effect is the lowest balance before and after."""
        before = self.get_dashboard().forecast
        self.repo.update_scheduled_item(item_id, **fields)
        self.run_daily_check(force=True)
        return self._effect(before)

    def _effect(self, before) -> dict:
        after = self.get_dashboard().forecast
        line = self._business().low_cash_line
        return {
            "before": round(before.lowest_with_today()[0]) if before else None,
            "after": round(after.lowest_with_today()[0]) if after else None,
            "risk_before": before.risk_level(line) if before else None,
            "risk_after": after.risk_level(line) if after else None,
        }

    def _basis_item(self, item: ScheduledItem, found: dict) -> dict:
        source = item.source or ""
        badge = (
            "file" if source.startswith("file:")
            else "example" if source == "example"
            else "confirmed" if item.status == "detected" and item.user_edited or item.status == "confirmed"
            else "statement" if item.status == "detected"
            else "owner"
        )  # fmt: skip
        detected = found.get(item.match_key) if item.match_key else None
        upcoming = expand_scheduled_items(
            [replace(item, paused=False)], self.today, self.today + timedelta(days=400)
        )
        return {
            "id": item.id,
            "label": item.label,
            "amount": item.amount,
            "direction": "in" if item.amount > 0 else "out",
            "how_often": recurring.describe(item.recurrence, item.due_date),
            "next": upcoming[0][0] if upcoming else None,
            "due": item.due_date,
            "badge": badge,
            "varies": bool(detected and detected.amount_varies),
            # a weekly payee the owner took out of the normal week: it can go back (#64)
            "weekly_payee": bool(detected and detected.in_normal_week and item.user_edited),
            "maybe": item.certainty == "maybe",
            "paused": item.paused,
            "end_date": item.end_date,
            "past_due": not item.recurrence and item.due_date < self.today,
            "category": item.category,
            # what it adds up to in the next 30 days (R.1: totals for money in and out)
            "next_30_days": round(
                (
                    sum(a for d, a, _ in upcoming if d < self.today + timedelta(days=30))
                    if not item.paused
                    else 0.0
                ),
                2,
            ),
        }

    def _update_suggestions(self, items: list[ScheduledItem], found: dict) -> list[dict]:
        """A payment the owner set themselves whose recent amount in the statement is different:
        suggested, never applied ("Rent was $950 the last 2 months, not $900. Update?")."""
        out = []
        seen = self.repo.get_profile(self._business().id).get("amount_set_with_statement", {})
        end = self.statement_end()
        for item in items:
            detected = found.get(item.match_key) if item.match_key else None
            if not (item.user_edited and detected) or detected.amount_varies:
                continue
            set_with = seen.get(str(item.id))
            if set_with and end and end <= date.fromisoformat(set_with):
                continue  # no newer statement since the owner set this amount
            if abs(detected.amount - item.amount) > 0.05 * abs(item.amount):
                out.append(
                    {"id": item.id, "label": item.label, "planned": item.amount, "found": detected.amount}
                )
        return out

    def _rhythm(self, business_id: int) -> dict:
        """A typical week of money in and out apart from the payments listed on the page (last 12
        weeks): the middle half of the weeks, and the busiest and slowest days for money in."""
        flows = self.repo.daily_in_out(business_id)
        if flows.empty:
            return {}
        flows = flows[flows["date"] >= pd.Timestamp(self.today - timedelta(weeks=12))]
        weeks = flows.set_index("date").resample("W").sum()
        weeks = weeks.iloc[1:-1] if len(weeks) > 4 else weeks  # drop the partial first and last weeks
        by_day = flows.assign(day=flows["date"].dt.dayofweek).groupby("day")["money_in"].mean()
        names = recurring.WEEKDAY_NAMES
        return {
            "in_low": round(float(weeks["money_in"].quantile(0.25)), 2),
            "in_high": round(float(weeks["money_in"].quantile(0.75)), 2),
            "out_low": round(float(weeks["money_out"].quantile(0.25)), 2),
            "out_high": round(float(weeks["money_out"].quantile(0.75)), 2),
            "busiest_day": names[int(by_day.idxmax())] if len(by_day) else None,
            "slowest_day": names[int(by_day.idxmin())] if len(by_day) > 1 else None,
            "weeks": len(weeks),
        }

    def _not_counted(self, business_id: int, found: dict) -> dict:
        moves = self.repo.internal_transfer_counts(business_id)
        return {
            "own_account_moves": moves.get("transfers", 0),
            "card_payments": moves.get("card_payments", 0),
            "some_months_only": [r.label for r in found.values() if r.seasonal],
            "paused": [i.label for i in self.repo.list_scheduled_items(business_id) if i.paused],
            "switched_off": [
                {
                    "label": i.label,
                    "amount": i.amount,
                    "why": "doubtful" if i.status == "doubtful" else "removed",
                }
                for i in self.repo.inactive_items(business_id)
            ],
        }

    def _next_month(self) -> dict:
        """Next calendar month (as far as the forecast reaches), split into the normal rhythm, regular
        payments and one-offs; the parts add up to the forecast's own total for those days."""
        forecast = self.get_dashboard().forecast
        if forecast is None:
            return {}
        first = (self.today.replace(day=1) + timedelta(days=32)).replace(day=1)
        last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        last = min(last, forecast.horizon_end)
        days = [p for p in forecast.points if first <= p.date <= last]
        total = sum(p.net_flow_p50 for p in days)
        events = self._dated_events(self.repo.list_scheduled_items(self._business().id), last)
        parts = {"recurring_in": 0.0, "recurring_out": 0.0, "one_off_in": 0.0, "one_off_out": 0.0}
        maybe_in = 0.0
        for e, item in events:
            if not first <= e.due_date <= last:
                continue
            if uncertain_income(e):  # only in some of the forecast's paths: shown apart, not added in
                maybe_in += e.amount
                continue
            kind = "recurring" if item.recurrence else "one_off"
            parts[f"{kind}_{'in' if e.amount > 0 else 'out'}"] += e.amount
        parts = {k: round(v, 2) for k, v in parts.items()}
        return {
            "first": first,
            "last": last,
            **parts,
            "maybe_in": round(maybe_in, 2),
            "rhythm": round(total - sum(parts.values()), 2),
            "total": round(total, 2),
        }

    # ------------------------------------------------------------ just say it (roadmap 2.4)
    def parse_plan_text(self, text: str) -> list[ProposedItem]:
        """What the owner wrote ("I'm buying a new oven for $7,500 on Nov 14") as plan items to
        confirm. Saves nothing."""
        if not text.strip():
            return []
        items, _ = self.translator.extract_plan_items(text, self.today)
        return items

    def check_proposals(self, arguments: dict, text: str) -> list[ProposedItem]:
        """The chat's proposed items, checked like any other (the amounts must be in the owner's words)."""
        return plan_text.read_tool_call(arguments, self.today, text or None)

    def add_plan_items(self, items: list[ProposedItem | dict], source: str = "owner") -> int:
        """Save the items the owner confirmed (Add). Each is checked again; items with a problem are
        refused, the rest are saved and the forecast reruns. Returns how many were added."""
        checked = [i if isinstance(i, ProposedItem) else plan_text.check_item(i, self.today) for i in items]
        checked = [plan_text.check_item({**i.to_dict()}, self.today) for i in checked]
        problems = [i for i in checked if not i.ready]
        if problems:
            raise ValueError(f"{problems[0].label or 'An item'}: {problems[0].problem}")
        business = self._business()
        self.repo.add_scheduled_items(
            business.id,
            [
                ScheduledItem(
                    label=i.label,
                    amount=round(i.signed_amount, 2),
                    due_date=i.due_date,
                    kind="receivable" if i.direction == "in" else "bill",
                    recurrence=plan_text.RECURRENCE[i.repeats],
                    source=source,
                    status="user",
                    certainty=i.certainty,
                )
                for i in checked
            ],
        )
        if checked:
            self.run_daily_check(force=True)
        return len(checked)
