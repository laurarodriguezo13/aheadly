"""App Core: orchestrates the daily run and serves insights to the UI (interface "Get Insights").

The Streamlit pages call only methods on this class. App Core talks to the
Repository, the Forecast Engine and the Insight Translator; it never talks to
an LLM or a bank API directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from aheadly.ai import categorizer, recurring
from aheadly.ai.forecast_engine import ForecastEngine, expand_scheduled_items, history_balances
from aheadly.ai.insight_translator import InsightTranslator
from aheadly.ai.llm_client import create_llm_client
from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
from aheadly.ai.tools import ToolDispatcher
from aheadly.config import Settings
from aheadly.core import alert_rules
from aheadly.core.examples import DEFAULT_EXAMPLE, load_example
from aheadly.core.transfers import Line, find_transfers
from aheadly.data.connectors.base import Connector
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

    # ------------------------------------------------------------ recurring (roadmap 2.3)
    def detected_recurring(self) -> list[recurring.Recurring]:
        """Every repeating payment and income found in the statements, with its rule."""
        lines = [
            recurring.TxLine(r[0], date.fromisoformat(r[1]), r[2], r[3], r[4], bool(r[5]))
            for r in self.repo.recurring_lines(self._business().id)
        ]
        return recurring.detect(lines, self.today)

    def recurring_table(self) -> list[dict]:
        """What the Accounts page lists: each regular payment and income, how often, and how the
        forecast uses it."""
        rows = []
        for r in self.detected_recurring():
            if r.internal:
                continue
            rows.append(
                {
                    "description": r.label,
                    "how_often": r.cadence,
                    "amount": r.amount,
                    "varies": r.amount_varies,
                    "next": r.next_due.isoformat() if r.next_due else "",
                    "in_forecast": "on its dates" if r.scheduled else "in the daily pattern",
                    "category": r.category,
                }
            )
        return sorted(
            rows, key=lambda row: (-abs(row["amount"]) if row["in_forecast"] == "on its dates" else 0)
        )

    def _detect_recurring(self, business_id: int) -> None:
        """Put each recurring payment on its real dates (as scheduled items) and take its past lines
        out of what the model learns from, so nothing is counted twice."""
        found = self.detected_recurring()
        existing = self.repo.list_scheduled_items(business_id)
        # the demo data (and an owner who typed their payroll) already has items for these kinds
        covered = {i.kind for i in existing if i.status != "detected" and i.recurrence} & SCHEDULED_CATEGORIES
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
        forecast.run_id = self.repo.save_forecast(business.id, forecast, self.settings.horizon_days)

        detected = alert_rules.detect_alerts(forecast, business, self._avg_monthly_outflow(), self.today)
        open_alerts = self.repo.list_alerts(business.id)
        summary = DailyRunSummary(ran=True, forecast=forecast)
        for facts in detected:
            text = self.translator.write_alert(facts.facts)
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
        business = self._business()
        parsed = [parse_adjustment(a) for a in adjustments]
        if not parsed:
            raise ValueError("A scenario needs at least one adjustment")
        items = self.repo.list_scheduled_items(business.id)
        adjusted = apply_adjustments(
            items, parsed, self.today, self.settings.horizon_days, self.weekly_sales()
        )
        baseline = self._baseline_forecast()
        scenario = self._forecast_for(adjusted)
        result = ScenarioResult(name, parsed, baseline, scenario, business.low_cash_line)
        result.scenario_id = self.repo.save_scenario(business.id, name, adjustments, result.summary(), False)
        return result

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
            if item.status != "detected"
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
        covered = {
            item.kind for item in self.repo.list_scheduled_items(business.id) if item.status != "detected"
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
        )

    def _events(self, end: date) -> list[tuple[date, float, str]]:
        """Dated money in and out from today to `end`, each payment once."""
        items = self._without_duplicates(self.repo.list_scheduled_items(self._business().id), end)
        return [(i.due_date, i.amount, i.label) for i in items]

    def _without_duplicates(self, items: list[ScheduledItem], end: date | None = None) -> list[ScheduledItem]:
        """A payment the owner told us about that is also one of the recurring ones found in the
        statement (the quarterly flour order, an insurer's claim) is counted once."""
        end = end or self.today + timedelta(days=self.settings.horizon_days - 1)
        events = [
            (when, amount, label, item.status == "detected")
            for item in items
            for when, amount, label in expand_scheduled_items([item], self.today, end)
        ]
        return [
            ScheduledItem(label, amount, when, source="forecast")
            for when, amount, label in recurring.drop_duplicates(events)
        ]

    def _avg_monthly_outflow(self) -> float:
        totals = self.repo.flow_totals(self._business().id, self.today - timedelta(days=90))
        return totals["money_out"] / 3

    def _prompt_context(self, business: Business) -> dict:
        labels = ", ".join(sorted({i.label for i in self.repo.list_scheduled_items(business.id)}))
        return {
            "business_name": business.name,
            "end_of_next_month": end_of_next_month(self.today).isoformat(),
            "owner_name": business.owner_name,
            "today": self.today.isoformat(),
            "currency": business.currency,
            "low_cash_line": round(business.low_cash_line),
            "scheduled_labels": labels or "none",
        }


def _kind(category: str | None, amount: float) -> str:
    """A scheduled item's kind from the category of the lines it comes from."""
    if category in ("payroll", "rent"):
        return category
    return "receivable" if amount > 0 else "bill"


def _adjustment_dict(adjustment) -> dict:
    params = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in adjustment.params.items()}
    return {"type": adjustment.type, **params}
