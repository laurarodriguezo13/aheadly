"""App Core: orchestrates the daily run and serves insights to the UI (interface "Get Insights").

The Streamlit pages call only methods on this class. App Core talks to the
Repository, the Forecast Engine and the Insight Translator; it never talks to
an LLM or a bank API directly.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

from aheadly.ai import categorizer, confidence, plan_text, recurring, seasons
from aheadly.ai.plan_text import ProposedItem
from aheadly.ai.forecast_engine import (
    ForecastEngine,
    expand_scheduled_items,
    history_balances,
    uncertain_income,
)
from aheadly.ai.insight_translator import InsightTranslator
from aheadly.ai.llm_client import create_llm_client
from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
from aheadly.ai.tools import ToolDispatcher
from aheadly.config import Settings
from aheadly.ai import templates
from aheadly.core import actions as alert_actions
from aheadly.core import alert_rules, onboarding, safe
from aheadly.core.examples import DEFAULT_EXAMPLE, load_example
from aheadly.core.transfers import Line, find_transfers
from aheadly.data.connectors.base import Connector
from aheadly.data.connectors import owner_files
from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.data.repository import Repository
from aheadly.domain import (
    SCHEDULED_CATEGORIES,
    Alert,
    Business,
    ChatAnswer,
    ForecastResult,
    ScenarioResult,
    ScheduledItem,
    end_of_next_month,
)

logger = logging.getLogger(__name__)


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
    unread_alerts: int = 0
    scheduled: list = field(default_factory=list)


class AppCore:
    def __init__(
        self,
        repo: Repository,
        engine: ForecastEngine,
        settings: Settings,
        llm=None,
        today: date | None = None,
    ):
        self.repo = repo
        self.engine = engine
        self.settings = settings
        self._today = today
        self._pending_time_zone: str | None = None  # from the browser, kept until a business exists
        self._backtests: dict = {}  # backtest error per history (roadmap 2.8)
        self._messages: dict[str, str] = {}  # drafted messages per facts (roadmap 3.2)
        self._fixes_cache: dict = {}  # suggested fixes for the latest forecast run (roadmap 3.3)
        self._pay_cache: dict = {}  # safe owner's pay for the latest forecast run (roadmap 3.4)
        self.translator = InsightTranslator(llm or create_llm_client(settings), ToolDispatcher(self))

    @property
    def today(self) -> date:
        """The forecast's first day: today, or the day after the statement's last transaction
        when the statement ends earlier (the days in between are not in the data)."""
        if self._today:
            return self._today
        real = self.real_today()
        end = self.statement_end()
        if end is not None and end + timedelta(days=1) < real:
            return end + timedelta(days=1)
        return real

    def real_today(self) -> date:
        """Today's date where the owner is (the server may be in another time zone, e.g. UTC)."""
        zone = self.time_zone
        return datetime.now(ZoneInfo(zone)).date() if zone else date.today()

    @property
    def time_zone(self) -> str | None:
        business = self.repo.get_business()
        saved = self.repo.get_profile(business.id).get("time_zone") if business else None
        return saved or self._pending_time_zone

    def set_time_zone(self, name: str | None) -> None:
        """The owner's time zone, read from their browser. Unknown names are ignored."""
        if not name:
            return
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            return
        self._pending_time_zone = name
        business = self.repo.get_business()
        if business and self.repo.get_profile(business.id).get("time_zone") != name:
            self.repo.save_profile(business.id, {"time_zone": name})

    def statement_end(self) -> date | None:
        """Date of the newest transaction uploaded (None before any upload)."""
        business = self.repo.get_business()
        return self.repo.last_transaction_date(business.id) if business else None

    def statement_lag_days(self) -> int:
        """Days missing between the statement's last transaction and yesterday (0 = up to date)."""
        end = self.statement_end()
        return max(0, (self.real_today() - end).days - 1) if end else 0

    # ------------------------------------------------------------ onboarding
    def status(self) -> AppStatus:
        business = self.repo.get_business()
        accounts = self.repo.list_accounts(business.id) if business else []
        return AppStatus(
            business=business,
            connected=bool(accounts),
            accounts=accounts,
            last_run_at=self.repo.last_run_at(business.id) if business else None,
            llm_provider=self.translator.provider_name,
            llm_model=self.settings.model_for_provider,
            forecast_model=self.engine.model_name,
        )

    def connect(self, connector: Connector) -> int:
        """Feature 1: link a data source once; transactions then live in the repository."""
        return self.connect_files([connector])

    def connect_files(self, connectors: list[Connector]) -> int:
        """Upload one or more statements. A statement that shares lines with an account already here
        is another period of that account (its balance is the newest file's); any other file is a
        new account (bank or credit card). Then transfers between the owner's own accounts are
        found, and the forecast runs once. Returns how many new transactions came in."""
        if not connectors:
            raise ValueError("Choose at least one bank statement.")
        profile = {"low_cash_line": self.settings.default_low_cash_line, **connectors[0].business_profile()}
        business = self.repo.get_business() or self.repo.create_business(**profile)
        if self._pending_time_zone:
            self.set_time_zone(self._pending_time_zone)
        added = 0
        for connector in connectors:
            payload = connector.sync()
            newest = max((t.date for t in payload.transactions), default=None)
            account_id = self.repo.account_with_any(
                business.id, [t.external_id for t in payload.transactions]
            )
            if account_id is None:
                account_id = self.repo.add_account(
                    business.id, connector.source, payload.account_name, payload.balance, payload.account_kind
                )
            else:
                last = self.repo.account_last_date(account_id)
                if newest is not None and (last is None or newest >= last):
                    self.repo.set_account_balance(account_id, payload.balance)
            added += self.repo.add_transactions(business.id, account_id, payload.transactions)
            if payload.scheduled_items:
                self.repo.add_scheduled_items(business.id, payload.scheduled_items)
        self._mark_internal_transfers(business.id)
        self._categorize(business.id)
        self._detect_recurring(business.id)
        logger.info("connected %s file(s): %s transactions", len(connectors), added)
        self.run_daily_check(force=True)
        breaks = sum(getattr(c, "balance_breaks", 0) or 0 for c in connectors)
        self.repo.save_profile(business.id, {"balance_breaks": breaks})  # for the confidence check (2.8)
        return added

    def load_example(self, slug: str = DEFAULT_EXAMPLE) -> int:
        """Roadmap 1.5: replace whatever is here with an example business, read exactly like an
        owner's upload (its statements) plus the upcoming payments its owner knows about."""
        example = load_example(slug)
        self.reset()
        business = self.repo.create_business(**example.profile)
        self.repo.save_profile(business.id, {"example": example.slug})
        self.repo.add_scheduled_items(business.id, example.upcoming)
        return self.connect_files(
            [
                CsvConnector(content, None, name, business_profile=example.profile)
                for name, content in example.statements
            ]
        )

    def example(self) -> str | None:
        """The example business being shown, or None for the owner's own data."""
        business = self.repo.get_business()
        return self.repo.get_profile(business.id).get("example") if business else None

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

    def answer_payee(self, payee: str, answer: str) -> str:
        """The owner explains a payee in their own words ("loan for the car lift"); returns the
        category it was put in."""
        category = categorizer.category_from_answer(answer)
        self.set_payee_rule(payee, category, answer)
        return category

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

    # ------------------------------------------------------------ onboarding questions (roadmap 2.7)
    def onboarding(self) -> dict:
        """The questions still to answer, in order, and how far the owner got. Answered and skipped
        questions are remembered (the owner can stop and come back)."""
        business = self._business()
        done = self.repo.get_profile(business.id).get("onboarding_done", [])
        pending = [q for q in self._questions() if q.id not in done]
        self.repo.save_profile(business.id, {"questions_left": len(pending)})
        return {"questions": pending, "done": len(done), "total": len(done) + len(pending)}

    def questions_left(self) -> int | None:
        """How many questions were left the last time they were worked out (cheap: for the sidebar);
        None before the first time."""
        business = self.repo.get_business()
        return self.repo.get_profile(business.id).get("questions_left") if business else None

    def answer_business(self, business_type: str, customers_pay: str = "") -> None:
        changes = {"business_type": business_type.strip(), "customers_pay": customers_pay.strip()}
        self.repo.save_profile(self._business().id, {k: v for k, v in changes.items() if v})
        self._question_done("business")

    def answer_seasons(
        self, busy: list[int], slow: list[int], changes: dict[int, float] | None = None
    ) -> None:
        self.set_seasons(busy, slow, changes)
        self._question_done("seasons")

    def answer_owner_pay(self, payee: str, is_owner_pay: bool) -> None:
        """Yes: every payment to it is the owner's pay (still money out, but one they can change)."""
        if is_owner_pay:
            self.set_payee_rule(payee, "owner_pay")
        self._question_done(f"owner_pay:{categorizer.match_key(payee)}")

    def answer_mystery(self, payee: str, category: str | None = None, words: str = "") -> str:
        """What a payee is: a category picked from the list, or the owner's own words (or both).
        Returns the category used."""
        if category:
            self.set_payee_rule(payee, category, words or payee)
        elif words.strip():
            category = self.answer_payee(payee, words)
        else:
            raise ValueError("Pick a category or say in your own words what it is.")
        self._question_done(f"mystery:{categorizer.match_key(payee)}")
        return category

    def skip_question(self, question_id: str) -> None:
        """Skipped: not asked again, but not counted as answered (confidence, roadmap 2.8)."""
        business = self._business()
        skipped = list(self.repo.get_profile(business.id).get("onboarding_skipped", []))
        if question_id not in skipped:
            self.repo.save_profile(business.id, {"onboarding_skipped": skipped + [question_id]})
        self._question_done(question_id, skipping=True)

    def example_answers(self) -> dict:
        """The example owner's own answers, to pre-fill the questions when trying the example."""
        example = self.example()
        return load_example(example).answers if example else {}

    def _question_done(self, question_id: str, skipping: bool = False) -> None:
        business = self._business()
        profile = self.repo.get_profile(business.id)
        skipped = profile.get("onboarding_skipped", [])
        if not skipping and question_id in skipped:  # answered after all (e.g. busy months, later)
            self.repo.save_profile(
                business.id, {"onboarding_skipped": [q for q in skipped if q != question_id]}
            )
        done = list(profile.get("onboarding_done", []))
        if question_id not in done:
            done.append(question_id)
        left = self.repo.get_profile(business.id).get("questions_left")
        changes = {"onboarding_done": done}
        if left:
            changes["questions_left"] = left - 1
        self.repo.save_profile(business.id, changes)

    def _questions(self) -> list[onboarding.Question]:
        business = self._business()
        end = self.statement_end() or self.today
        since = end - timedelta(days=90)
        how_often = {}
        for item in self.detected_recurring():
            if item.rules and item.next_dates:
                rule = recurring.recurrence_for(item.rules[0])
                how_often[item.match_key] = recurring.describe(rule, item.next_dates[0])
        # one-off small change isn't worth a question; anything that repeats is (it's in the forecast)
        floor = 0.01 * self.repo.flow_totals(business.id, since)["money_out"]
        payees = [
            p
            for p in self.repo.uncategorized_payees(business.id, since)
            if abs(p["total"]) >= floor or categorizer.match_key(p["description"]) in how_often
        ]
        names = [p["description"] for p in payees[: onboarding.MAX_MYSTERIES + 2]]
        return onboarding.build(
            self.repo.get_profile(business.id), payees, self._category_suggestions(names), how_often
        )

    def _category_suggestions(self, payees: list[str]) -> dict[str, tuple[str, str]]:
        """The connected model's guess for each payee (names only, one call, kept so reruns don't
        call it again). Nothing is applied until the owner confirms."""
        if not payees:
            return {}
        business = self._business()
        kept = self.repo.get_profile(business.id).get("category_suggestions", {})
        missing = [p for p in payees if p not in kept]
        if missing:
            found = self.translator.suggest_categories(missing)
            kept = {**kept, **{p: list(found.get(p, ("", ""))) for p in missing}}
            self.repo.save_profile(business.id, {"category_suggestions": kept})
        return {p: (c, why) for p, (c, why) in kept.items() if p in payees and c}

    # ------------------------------------------------------------ busy and slow months (roadmap 2.7)
    def seasons(self) -> dict:
        """The owner's busy and slow months, what the statement says about each (last time it came,
        how much more or less money came in than in a normal month) and the change the forecast uses."""
        business = self._business()
        profile = self.repo.get_profile(business.id)
        busy, slow = profile.get("busy_months", []), profile.get("slow_months", [])
        money_in = seasons.daily_money_in(self.repo.daily_in_out(business.id))
        found = seasons.month_estimates(money_in, busy, slow)
        own = {int(m): v for m, v in profile.get("season_changes", {}).items()}
        months = [
            {
                "month": m,
                "name": seasons.MONTH_NAMES[m],
                "kind": "busy" if m in busy else "slow",
                "from_statement": found.get(m),
                "owners": own.get(m),
                "used": own[m] if m in own else _agreeing(found.get(m), m in busy),
            }
            for m in sorted(set(busy) | set(slow))
        ]
        return {
            "answered": "busy_months" in profile,
            "months": months,
            "level": seasons.recent_level(money_in),
        }

    def season_estimates(self, busy: list[int], slow: list[int]) -> dict[int, float | None]:
        """What the statement says about months the owner is about to mark (before saving)."""
        money_in = seasons.daily_money_in(self.repo.daily_in_out(self._business().id))
        return seasons.month_estimates(money_in, busy, slow)

    def set_seasons(self, busy: list[int], slow: list[int], changes: dict[int, float] | None = None) -> None:
        """Save the owner's answer. `changes`: their own estimate for a month (+0.5 = 50% more money
        in than a normal month), replacing the one from the statement. The forecast reruns."""
        busy = sorted({int(m) for m in busy})
        slow = sorted({int(m) for m in slow} - set(busy))
        own = {str(m): seasons.clamp(float(v)) for m, v in (changes or {}).items() if v is not None}
        self.repo.save_profile(
            self._business().id, {"busy_months": busy, "slow_months": slow, "season_changes": own}
        )
        self.run_daily_check(force=True)

    def _month_shift(self, business_id: int) -> dict[int, float]:
        profile = self.repo.get_profile(business_id)
        if not profile.get("busy_months") and not profile.get("slow_months"):
            return {}
        info = self.seasons()
        return seasons.daily_shift(info["level"], {m["month"]: m["used"] for m in info["months"]})

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
        """The owner changes an item (amount, label, next date, end date). From now on it's theirs:
        a later upload suggests changes but never overwrites them. Returns the effect."""
        item = self._own_item(item_id)
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

    def end_plan_item(self, item_id: int, end: date | None) -> dict:
        """It stops after `end` (None: it goes on again)."""
        self._own_item(item_id)
        return self._change(item_id, end_date=end, user_edited=True)

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
            "maybe": item.certainty == "maybe",
            "paused": item.paused,
            "end_date": item.end_date,
            "past_due": not item.recurrence and item.due_date < self.today,
            "category": item.category,
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

    # ------------------------------------------------------------ owner's files (roadmap 2.5)
    def read_owner_file(
        self, content: bytes, filename: str, kind: str | None = None, columns: dict[str, str] | None = None
    ) -> owner_files.OwnerFile:
        """Read a file the owner keeps and say what it is and what it would add. Saves nothing.
        `kind`: what the owner says it is, when the app guessed wrong or couldn't tell; `columns`:
        which of the file's columns holds what (role → title), when the titles didn't say."""
        read = owner_files.read_owner_file(content, filename, self.today, kind, columns)
        if read.kind is None and kind is None and read.headers:
            guess = self.translator.classify_owner_file(read.headers)
            if guess:
                kind_guess, columns = guess
                read = owner_files.read_owner_file(content, filename, self.today, kind_guess, columns)
                read.details["kind_from"] = "ai"
        if read.kind == "employees" and not read.problem:
            read.details["payroll_found_per_month"] = self._payroll_per_month()
        if read.items:
            planned = [
                i for i in self.repo.list_scheduled_items(self._business().id) if not _from_statement(i)
            ]
            read.details["already_planned"] = sum(1 for i in read.items if _already_planned(i, planned))
        return read

    def use_owner_file(self, read: owner_files.OwnerFile) -> int:
        """The owner confirmed the file: its payments go into the plan (skipping ones already there)
        and the file is remembered. Returns how many items were added."""
        if read.problem or read.kind is None:
            raise ValueError(read.problem or "Pick what this file is first.")
        business = self._business()
        planned = [i for i in self.repo.list_scheduled_items(business.id) if not _from_statement(i)]
        new = [i for i in read.items if not _already_planned(i, planned)]
        self.repo.add_scheduled_items(business.id, new)
        self.repo.record_uploaded_file(business.id, read.name, read.kind, read.columns)
        if new:
            self.run_daily_check(force=True)
        return len(new)

    def uploaded_files(self) -> list[dict]:
        return self.repo.uploaded_files(self._business().id)

    def _payroll_per_month(self) -> float:
        """Pay found in the statement as payroll (wages, not bonuses or social security), per month."""
        per_month = {"weekly": 52 / 12, "every two weeks": 26 / 12, "twice a month": 2.0, "monthly": 1.0}
        total = 0.0
        for r in self.detected_recurring():
            wages = any(w in r.match_key for w in ("nomina", "payroll", "salari", "sueldo", "wages"))
            extra = any(w in r.match_key for w in ("prima", "pila", "aportes", "temporada", "bonus"))
            if r.category == "payroll" and wages and not extra and not r.seasonal and r.cadence in per_month:
                total += -r.amount * per_month[r.cadence]
        return round(total, 2)

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
            if not found_item.scheduled or _kind(found_item.category, found_item.amount) in covered:
                continue
            if found_item.match_key in edited:
                keep_links[edited[found_item.match_key]] = found_item.transaction_ids
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

    # ------------------------------------------------------------- daily run
    def ensure_fresh(self) -> DailyRunSummary:
        """Run today's check on app load if the last one is older than 24 h."""
        last = self.repo.last_run_at(self._business().id)
        max_age = timedelta(hours=self.settings.daily_run_max_age_hours)
        if last is not None and datetime.now(timezone.utc) - last < max_age:
            return DailyRunSummary(ran=False)
        return self.run_daily_check(force=True)

    def run_daily_check(self, force: bool = False) -> DailyRunSummary:
        """Activity diagram: sync → forecast → risk or idle cash? → write alert → send alert."""
        if not force:
            return self.ensure_fresh()
        business = self._business()
        forecast = self._baseline_forecast()
        forecast.run_id = self.repo.save_forecast(
            business.id, forecast, self.settings.horizon_days, business.low_cash_line
        )

        detected = alert_rules.detect_alerts(forecast, business, self._avg_monthly_outflow(), self.today)
        open_alerts = self.repo.list_alerts(business.id)
        summary = DailyRunSummary(ran=True, forecast=forecast)
        for facts in detected:
            text = self.translator.write_alert(facts.facts)
            text.actions = self._actions_for(facts.facts, forecast)
            duplicate = alert_rules.find_duplicate(open_alerts, facts)
            if duplicate:
                self.repo.update_alert(
                    duplicate.id,
                    facts.severity,
                    facts.weeks_ahead,
                    facts.facts,
                    text.title,
                    text.body,
                    text.actions,
                )
                summary.alerts_updated += 1
            else:
                self.repo.add_alert(
                    business.id,
                    forecast.run_id,
                    facts.type,
                    facts.severity,
                    facts.weeks_ahead,
                    facts.facts,
                    text.title,
                    text.body,
                    text.actions,
                )
                summary.alerts_raised += 1
        detected_types = {f.type for f in detected}
        for alert_type in {a.type for a in open_alerts} - detected_types:
            summary.alerts_resolved += self.repo.resolve_alerts(business.id, alert_type)
        logger.info(
            "daily check: raised=%s updated=%s resolved=%s",
            summary.alerts_raised,
            summary.alerts_updated,
            summary.alerts_resolved,
        )
        return summary

    # ------------------------------------------------------------- dashboard
    def get_dashboard(self) -> Dashboard:
        business = self._business()
        balance = self.repo.current_balance(business.id)
        forecast = self.repo.latest_forecast(business.id)
        if forecast is not None:  # stored runs do not keep the scheduled events; recompute them
            forecast.scheduled = self._events(forecast.horizon_end)
        history = history_balances(self.repo.daily_net_flow(business.id), balance)
        upcoming = [e for e in (forecast.scheduled if forecast else []) if e[1] < 0]
        # "next big payment": the soonest one at least a quarter the size of the biggest ahead
        # (not this week's $449 flour delivery when a $7,500 oven is due in three days)
        biggest = -min((e[1] for e in upcoming), default=0.0)
        big = [e for e in upcoming if -e[1] >= 0.25 * biggest]
        next_payment = min(big, key=lambda e: (e[0], e[1])) if big else None
        return Dashboard(
            business=business,
            balance=balance,
            forecast=forecast,
            history=history,
            alerts=self.repo.list_alerts(business.id),
            next_payment=next_payment,
            unread_alerts=self.repo.unread_alert_count(business.id),
            scheduled=forecast.scheduled if forecast else [],
        )

    # ---------------------------------------------------------------- alerts
    def get_alerts(self, open_only: bool = True) -> list[Alert]:
        return self.repo.list_alerts(self._business().id, open_only=open_only)

    def unread_alert_count(self) -> int:
        business = self.repo.get_business()
        return self.repo.unread_alert_count(business.id) if business else 0

    def mark_alert_read(self, alert_id: int) -> None:
        self.repo.mark_alert_read(alert_id)

    def dismiss_alert(self, alert_id: int) -> None:
        self.repo.dismiss_alert(alert_id)

    # ------------------------------------------------------------------ chat
    def ask(self, question: str) -> ChatAnswer:
        business = self._business()
        history = self.repo.list_chat_messages(business.id)
        answer = self.translator.answer(question, history, self._prompt_context(business))
        self.repo.add_chat_message(business.id, "user", question)
        self.repo.add_chat_message(business.id, "assistant", answer.text, answer.tool_names)
        return answer

    def chat_history(self) -> list[dict]:
        return self.repo.list_chat_messages(self._business().id)

    def clear_chat(self) -> None:
        self.repo.clear_chat(self._business().id)

    # --------------------------------------------------------------- what-if
    def run_what_if(self, adjustments: list[dict], name: str = "Scenario") -> ScenarioResult:
        result = self._scenario(adjustments, name)
        result.scenario_id = self.repo.save_scenario(
            self._business().id, name, adjustments, result.summary(), False
        )
        return result

    def _scenario(
        self, adjustments: list[dict], name: str = "Scenario", baseline: ForecastResult | None = None
    ) -> ScenarioResult:
        """A what-if without keeping it in the owner's history (used to measure actions, roadmap 3.2)."""
        business = self._business()
        parsed = [parse_adjustment(a) for a in adjustments]
        if not parsed:
            raise ValueError("A scenario needs at least one adjustment")
        items = self.repo.list_scheduled_items(business.id)
        adjusted = apply_adjustments(
            items, parsed, self.today, self.settings.horizon_days, self.weekly_sales()
        )
        baseline = baseline or self._baseline_forecast()
        scenario = self._forecast_for(adjusted)
        return ScenarioResult(name, parsed, baseline, scenario, business.low_cash_line)

    # ------------------------------------------------------------- actions (3.2)
    def _actions_for(self, facts: dict, forecast: ForecastResult) -> list[dict]:
        """2–3 actions for an alert: worked out and measured by code when it can (roadmap 3.2–3.3),
        general advice (without a what-if) to fill up to two, and for idle cash."""
        generic = templates.alert_text(facts)["actions"]
        if facts["type"] != "shortfall":
            return generic
        found = self._fixes(forecast)
        return found + generic[: max(0, 2 - len(found))]

    def _fixes(self, baseline: ForecastResult) -> list[dict]:
        business = self._business()
        return alert_actions.build(
            baseline,
            business.low_cash_line,
            self.repo.list_scheduled_items(business.id),
            self.today,
            self.today + timedelta(days=self.settings.horizon_days - 1),
            lambda adjustments: self._scenario(adjustments, "Suggested fix", baseline=baseline),
            self.weekly_sales(),
        )

    def suggested_fixes(self) -> list[dict]:
        """Roadmap 3.3: tested suggestions whenever the status isn't safe (also "watch", which has
        no alert). Worked out once per forecast run."""
        business = self._business()
        run = self.repo.latest_forecast(business.id)
        key = (run.run_id if run else None, business.low_cash_line)
        if self._fixes_cache.get("key") != key:
            self._fixes_cache = {"key": key, "fixes": self._fixes(self._baseline_forecast())}
        return self._fixes_cache["fixes"]

    # --------------------------------------------------------- safe to spend (3.4)
    def safe_to_spend(self) -> dict:
        """The biggest one-off payment today that keeps even a bad month above the line."""
        business = self._business()
        forecast = self.repo.latest_forecast(business.id) or self._baseline_forecast()
        return safe.safe_to_spend(forecast, business.low_cash_line)

    def safe_owner_pay(self) -> dict | None:
        """The biggest pay per payment for the owner that keeps even a bad month above the line
        (None until the owner said which transfer is their pay). Worked out once per forecast run."""
        business = self._business()
        item = safe.owner_pay_item(self.repo.list_scheduled_items(business.id))
        if item is None:
            return None
        run = self.repo.latest_forecast(business.id)
        key = (run.run_id if run else None, business.low_cash_line, item.label, item.amount)
        if self._pay_cache.get("key") != key:
            baseline = self._baseline_forecast()
            now = -item.amount

            def worst_after(pay: float) -> float:
                change = {
                    "type": "recurring_change",
                    "label": item.label,
                    "amount_delta": round(now - pay, 2),
                    "start_date": self.today.isoformat(),
                }
                return self._scenario([change], "Safe pay", baseline=baseline).scenario.min_p10

            amount = safe.safe_owner_pay(
                item, business.low_cash_line, worst_after, baseline.min_p10 - business.low_cash_line
            )
            self._pay_cache = {
                "key": key,
                "pay": {
                    "label": item.label,
                    "now": round(now),
                    "safe": amount,
                    "how_often": recurring.describe(item.recurrence, item.due_date),
                },
            }
        return self._pay_cache["pay"]

    def safe_numbers(self) -> dict:
        """What the chat may say about safe spending and pay (every number from code)."""
        spend = self.safe_to_spend()
        pay = self.safe_owner_pay()
        return {
            "horizon_weeks": self.settings.horizon_days // 7,
            "safe_to_spend_now": spend["amount"],
            "low_cash_line": spend["low_cash_line"],
            "lowest_worst_case": spend["lowest_worst_case"],
            "owner_pay": (
                {
                    "payment": pay["label"],
                    "now_per_payment": pay["now"],
                    "safe_per_payment": pay["safe"],
                    "how_often": pay["how_often"],
                }
                if pay
                else None
            ),
        }

    def still_short(self) -> int | None:
        """How much the base case still misses the line even after the best suggestion (3.6 helps then)."""
        return alert_actions.still_short(self.suggested_fixes(), self._business().low_cash_line)

    def draft_message(self, action: dict) -> str:
        """A message for the owner to copy and send (the app never sends it). Written once per action."""
        if action.get("kind") not in alert_actions.MESSAGE_KINDS:
            raise ValueError("This suggestion has no message to draft")
        business = self._business()
        facts = alert_actions.message_facts(action, business.name, business.owner_name)
        key = json.dumps(facts, sort_keys=True)
        if key not in self._messages:
            self._messages[key] = self.translator.draft_message(facts)
        return self._messages[key]

    def explain_scenario(self, result: ScenarioResult) -> str:
        return self.translator.explain_scenario(result.summary(), self._prompt_context(self._business()))

    def save_plan(self, result: ScenarioResult) -> DailyRunSummary:
        """Storyboard frame 6: the scenario becomes the plan; forecast and alerts refresh."""
        business = self._business()
        items = apply_adjustments(
            self.repo.list_scheduled_items(business.id),
            result.adjustments,
            self.today,
            self.settings.horizon_days,
            self.weekly_sales(),
        )
        self.repo.replace_scheduled_items(business.id, items)  # removed ones are kept, switched off
        self.repo.save_scenario(
            business.id,
            result.name,
            [_adjustment_dict(a) for a in result.adjustments],
            result.summary(),
            True,
        )
        return self.run_daily_check(force=True)

    def saved_scenarios(self) -> list[dict]:
        return self.repo.list_scenarios(self._business().id)

    # -------------------------------------------------------------- settings
    def set_low_cash_line(self, value: float) -> None:
        if value < 0:
            raise ValueError("The low cash line cannot be negative")
        self.repo.update_low_cash_line(self._business().id, value)
        self.run_daily_check(force=True)

    def backtest(self) -> dict[str, float]:
        return self.engine.backtest(self._model_history(self._business()))

    def reset(self) -> None:
        self.repo.reset()

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
        }

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
        self, category: str | None = None, since: str | None = None, limit: int = 10
    ) -> list[dict]:
        since_date = date.fromisoformat(since) if since else None
        df = self.repo.list_transactions(self._business().id, since_date, category, max(1, min(50, limit)))
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
            }
            for a in self.get_alerts()
        ]

    # -------------------------------------------------------------- internals
    def _model_history(self, business: Business):
        """What the forecast learns from: history minus the categories that scheduled items already cover.

        Demo data has payroll/rent/bills as scheduled items, so they leave the history; a plain
        bank export has no scheduled items, so everything stays in and is forecast from the past.
        """
        # items found in the statement (even once the owner edits them) take out only their own lines
        covered = {
            item.kind for item in self.repo.list_scheduled_items(business.id) if not _from_statement(item)
        } & SCHEDULED_CATEGORIES
        return self.repo.daily_net_flow(business.id, exclude_categories=covered, exclude_linked=True)

    def _business(self) -> Business:
        business = self.repo.get_business()
        if business is None:
            raise RuntimeError("No business connected yet. Use the Accounts page first.")
        return business

    def _baseline_forecast(self) -> ForecastResult:
        return self._forecast_for(self.repo.list_scheduled_items(self._business().id))

    def _forecast_for(self, scheduled_items) -> ForecastResult:
        business = self._business()
        history = self._model_history(business)
        return self.engine.forecast(
            history,
            self.repo.current_balance(business.id),
            self._without_duplicates(scheduled_items),
            self.today,
            self.settings.horizon_days,
            month_shift=self._month_shift(business.id),
        )

    def _events(self, end: date) -> list[tuple[date, float, str]]:
        """Dated money in and out from today to `end`, each payment once."""
        items = self._without_duplicates(self.repo.list_scheduled_items(self._business().id), end)
        return [(i.due_date, i.amount, i.label) for i in items]

    def _without_duplicates(self, items: list[ScheduledItem], end: date | None = None) -> list[ScheduledItem]:
        """A payment the owner told us about that is also one of the recurring ones found in the
        statement (the quarterly flour order, an insurer's claim) is counted once. Each dated event
        keeps how sure it is (a "maybe" income arrives in only some of the forecast's paths)."""
        return [event for event, _item in self._dated_events(items, end)]

    def _dated_events(
        self, items: list[ScheduledItem], end: date | None = None
    ) -> list[tuple[ScheduledItem, ScheduledItem]]:
        """Each dated payment once, next to the plan item it came from."""
        end = end or self.today + timedelta(days=self.settings.horizon_days - 1)
        events = [
            (when, amount, label, _from_statement(item), item)
            for item in items
            for when, amount, label in expand_scheduled_items([item], self.today, end)
        ]
        moves = self._how_items_moved()
        return [
            (
                ScheduledItem(
                    label,
                    amount,
                    when,
                    kind=item.kind,
                    source="forecast",
                    certainty=item.certainty,
                    likelihood=item.likelihood,
                    spread=moves.get(item.id, (0.0, 0))[0],
                    jitter_days=moves.get(item.id, (0.0, 0))[1],
                ),
                item,
            )
            for when, amount, label, item in recurring.drop_duplicates(events)
        ]

    def _how_items_moved(self) -> dict[int, tuple[float, int]]:
        """For each payment found in the statement (3+ times): how much its amount spread (as a share
        of the typical amount) and how many days early or late it usually came, from the lines it
        explains. An amount the owner set themselves is theirs: no spread (roadmap 2.8)."""
        lines = self.repo.linked_lines(self._business().id)
        if lines.empty:
            return {}
        set_by_owner = self.repo.get_profile(self._business().id).get("amount_set_with_statement", {})
        edited = {int(k) for k in set_by_owner}
        out = {}
        for item_id, group in lines.groupby("scheduled_item_id"):
            if len(group) < 3:
                continue
            amounts = group["amount"].abs().to_numpy()
            typical = float(np.median(amounts))
            spread = 0.0 if item_id in edited or typical == 0 else float(np.std(amounts[-6:]) / typical)
            gaps = np.diff(np.sort(group["date"].to_numpy())).astype("timedelta64[D]").astype(int)
            jitter = int(min(5, round(float(np.std(gaps[-6:])) / 2))) if len(gaps) >= 2 else 0
            if spread > 0.02 or jitter:
                out[int(item_id)] = (round(min(spread, 0.5), 3) if spread > 0.02 else 0.0, jitter)
        return out

    def _avg_monthly_outflow(self) -> float:
        totals = self.repo.flow_totals(self._business().id, self.today - timedelta(days=90))
        return totals["money_out"] / 3

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
        }


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
