"""Understanding the statement: categories, recurring payments, weekly payees, own-account moves (2.2, 2.3, 3.8)."""

from __future__ import annotations

import logging
from datetime import date, timedelta


from aheadly.ai import categorizer, recurring
from aheadly.core.transfers import Line, find_transfers
from aheadly.domain import (
    SCHEDULED_CATEGORIES,
    ScheduledItem,
)

from aheadly.core.areas.shared import (
    _from_statement,
    _kind,
)

logger = logging.getLogger(__name__)


class UnderstandingMixin:
    """Part of `AppCore` (issue 14): understanding the statement: categories, recurring payments, weekly payees, own-account moves (2.2, 2.3, 3.8)."""

    # ------------------------------------------------------------ categories (roadmap 2.2)
    def set_payee_rule(self, payee: str, category: str, label: str = "") -> int:
        """The owner says what a payee is ("TRANSF 0045 REF 88213" → loan). Every line that mentions
        it, now and in later uploads, gets that category; the owner's answer always wins.
        Returns how many lines changed."""
        if category not in categorizer.CATEGORIES:
            raise ValueError(f"Unknown category {category!r}.")
        key = categorizer.match_key(payee)
        if not key:
            raise ValueError("Say which payee or description this is about.")
        business = self._business()
        self.repo.save_payee_rule(business.id, key, category, label or payee)
        changed = self._categorize(business.id)
        if changed:
            self._detect_recurring(business.id)  # an item's kind follows its category
            self.run_daily_check(force=True)
        return changed

    def monthly_category_totals(self) -> dict[str, dict[str, float]]:
        return self.repo.monthly_category_totals(self._business().id)

    def weekly_sales(self, weeks: int = 8) -> float:
        """Average weekly sales over the last `weeks` weeks (money in, if nothing is called sales)."""
        business = self._business()
        start = self.today - timedelta(weeks=weeks)
        sales = self.repo.category_total(business.id, "sales", start, self.today)
        if sales <= 0:
            sales = self.repo.flow_totals(business.id, start)["money_in"]
        return round(sales / weeks, 2)

    # ------------------------------------------------------------ recurring (roadmap 2.3)
    def detected_recurring(self) -> list[recurring.Recurring]:
        """Every repeating payment and income found in the statements, with its rule."""
        lines = [
            recurring.TxLine(r[0], date.fromisoformat(r[1]), r[2], r[3], r[4], bool(r[5]))
            for r in self.repo.recurring_lines(self._business().id)
        ]
        return recurring.detect(lines, self.today)

    def _detect_recurring(self, business_id: int) -> None:
        """Put each recurring payment on its real dates (as scheduled items) and take its past lines
        out of what the model learns from, so nothing is counted twice."""
        found = self.detected_recurring()
        existing = self.repo.list_scheduled_items(business_id)
        # the demo data (and an owner who typed their payroll) already has items for these kinds
        covered = {i.kind for i in existing if not _from_statement(i) and i.recurrence} & SCHEDULED_CATEGORIES
        edited = self.repo.edited_items_by_key(business_id)
        items, keep_links = [], {}
        for found_item in found:
            if _kind(found_item.category, found_item.amount) in covered:
                continue
            if found_item.match_key in edited:  # also a weekly payee the owner planned on its own (#64)
                keep_links[edited[found_item.match_key]] = found_item.transaction_ids
                continue
            if not found_item.scheduled:
                continue
            for i, (rule, nominal) in enumerate(zip(found_item.rules, found_item.next_dates)):
                item = ScheduledItem(
                    label=found_item.label,
                    amount=found_item.amount,
                    due_date=nominal,
                    kind=_kind(found_item.category, found_item.amount),
                    recurrence=recurring.recurrence_for(rule),
                    source="statement",
                    status="detected",
                    certainty=found_item.certainty,
                    category=found_item.category,
                    match_key=found_item.match_key,
                )
                # every line of the payee is linked to its first item (that's what leaves the history)
                items.append((item, found_item.transaction_ids if i == 0 else []))
        self.repo.replace_detected_items(business_id, items, keep_links)

    # ------------------------------------------- weekly payees in the normal week (DECISIONS #64)
    def weekly_payees(self) -> list[dict]:
        """Payees paid every week whose amount changes each time: they sit in the normal
        week the forecast learns from, so the owner couldn't change or pause them. Each with what it
        came to a week in the last 8 weeks of the statement, so the owner can plan it on its own."""
        business = self._business()
        planned = self.repo.edited_items_by_key(business.id)
        end = self.statement_end() or self.today
        out = []
        for found in self.detected_recurring():
            # payments only (money in every week is the normal week itself), and not taxes or fees
            if not found.in_normal_week or found.match_key in planned or found.direction != "out":
                continue
            if found.category in ("taxes", "bank_fees"):
                continue
            per_week = self._per_week(found, end)
            if abs(per_week) < 1:
                continue
            out.append(
                {
                    "match_key": found.match_key,
                    "label": found.label,
                    "direction": found.direction,
                    "how_often": found.cadence,
                    "per_week": per_week,
                    "times": found.occurrences,
                }
            )
        return sorted(out, key=lambda p: -abs(p["per_week"]))

    def _per_week(self, found: recurring.Recurring, end: date) -> float:
        """What a payee came to a week over the statement's last 8 weeks (weeks without it count)."""
        first = self.repo.statement_summary(self._business().id)["first"]
        since = max(end - timedelta(weeks=8), date.fromisoformat(first) - timedelta(days=1) if first else end)
        weeks = max(1.0, (end - since).days / 7)
        ids = set(found.transaction_ids)
        lines = [r for r in self.repo.recurring_lines(self._business().id) if r[0] in ids]
        total = sum(r[2] for r in lines if since < date.fromisoformat(r[1]) <= end)
        return round(total / weeks, 2)

    def plan_weekly_payee(self, match_key: str) -> dict:
        """The owner plans a weekly payee on its own: a regular payment at what it came to a week
        (spread over its days of the week), taken out of the normal week. From then on it can be
        changed, paused, given an end date or a later next date like any regular payment. Returns
        the effect on the lowest balance."""
        business = self._business()
        found = next((f for f in self.weekly_payees() if f["match_key"] == match_key), None)
        detected = next((r for r in self.detected_recurring() if r.match_key == match_key), None)
        if found is None or detected is None:
            raise ValueError("That payment isn't a weekly one in your normal week any more.")
        before = self.get_dashboard().forecast
        share = round(found["per_week"] / len(detected.rules), 2)
        self.repo.add_scheduled_items(
            business.id,
            [
                ScheduledItem(
                    label=detected.label,
                    amount=share,
                    due_date=nominal,
                    kind=_kind(detected.category, detected.amount),
                    recurrence="weekly",
                    source="statement",
                    status="detected",
                    category=detected.category,
                    match_key=match_key,
                    user_edited=True,
                )
                for nominal in detected.next_dates
            ],
        )
        self._detect_recurring(business.id)  # links its past lines: they leave the normal week
        self.run_daily_check(force=True)
        return self._effect(before)

    def _in_normal_week(self, adjustments) -> str | None:
        """A what-if about a weekly payee still in the normal week can't change it: say how to (#64)."""
        names = [str(a.params.get("label", "")).lower().strip() for a in adjustments]
        for payee in self.weekly_payees():
            words = recurring._words(payee["label"])
            if any(n and (n in payee["match_key"] or words & recurring._words(n)) for n in names):
                return (
                    f"'{payee['label']}' is a weekly payment with a different amount each time, so it is part "
                    f"of the normal week (about {abs(payee['per_week']):,.0f} a week), not a payment I can "
                    "change in a what-if. Tell the owner: on How we built your forecast, under Your normal "
                    "week, 'Plan it on its own' makes it a regular payment they can change, pause or start "
                    "again later; then I can test it."
                )
        return None

    def back_to_normal_week(self, item_id: int) -> dict:
        """Undo `plan_weekly_payee`: the payee goes back into the normal week."""
        item = self._own_item(item_id)
        if not item.match_key:
            raise ValueError("Only a payment found in your statement can go back to your normal week.")
        before = self.get_dashboard().forecast
        self.repo.forget_items(self._business().id, item.match_key)
        self._detect_recurring(self._business().id)
        self.run_daily_check(force=True)
        return self._effect(before)

    def _categorize(self, business_id: int) -> int:
        rules = [categorizer.PayeeRule(*r) for r in self.repo.payee_rules(business_id)]
        updates, own_money = [], []
        for row in self.repo.categorization_lines(business_id):
            line = categorizer.Line(*row[:5], bool(row[5]))
            category, source = categorizer.categorize(line, rules)
            if (category, source) != (line.category, line.category_source):
                updates.append((category, source, line.id))
            if category == "transfer_internal" and not line.is_internal_transfer:
                own_money.append(line.id)  # the owner says it's their own money: not income or spending
        self.repo.set_categories(updates)
        if own_money:
            self.repo.mark_internal_transfers(own_money, [])
        return len(updates)

    def internal_transfer_counts(self) -> dict[str, int]:
        business = self.repo.get_business()
        return (
            self.repo.internal_transfer_counts(business.id)
            if business
            else {"transfers": 0, "card_payments": 0}
        )

    def _mark_internal_transfers(self, business_id: int) -> None:
        lines = [Line(*row) for row in self.repo.transfer_candidates(business_id)]
        pairs = find_transfers(lines)
        self.repo.mark_internal_transfers(
            [i for p in pairs for i in (p.out_id, p.in_id)],
            [i for p in pairs if p.card_payment for i in (p.out_id, p.in_id)],
        )
