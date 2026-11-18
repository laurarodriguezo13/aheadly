"""App Core: orchestrates the daily run and serves insights to the UI (interface "Get Insights").

The Streamlit pages call only methods on this class. App Core talks to the
Repository, the Forecast Engine and the Insight Translator; it never talks to
an LLM or a bank API directly.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np

from aheadly.ai import recurring
from aheadly.ai.forecast_engine import (
    ForecastEngine,
    expand_scheduled_items,
    history_balances,
)
from aheadly.ai.insight_translator import InsightTranslator
from aheadly.ai.llm_client import create_llm_client
from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
from aheadly.ai.tools import ToolDispatcher
from aheadly.config import Settings
from aheadly.ai import templates
from aheadly.core import actions as alert_actions
from aheadly.core import alert_rules
from aheadly.data.repository import Repository
from aheadly.domain import (
    chance_pct,
    SCHEDULED_CATEGORIES,
    Alert,
    Business,
    NEXT_MONTH,
    ChatAnswer,
    ForecastResult,
    ScenarioResult,
    ScheduledItem,
    end_of_next_month,
)

from aheadly.core.areas.shared import (
    AppStatus,
    DailyRunSummary,
    Dashboard,
    NEVER_PAIRED,
    _from_statement,
    _adjustment_dict,
)
from aheadly.core.areas.files import FilesMixin
from aheadly.core.areas.understanding import UnderstandingMixin
from aheadly.core.areas.questions import QuestionsMixin
from aheadly.core.areas.basis import BasisMixin
from aheadly.core.areas.insights import InsightsMixin
from aheadly.core.areas.suggestions import SuggestionsMixin
from aheadly.core.areas.chat_facts import ChatFactsMixin

logger = logging.getLogger(__name__)


class AppCore(
    FilesMixin,
    UnderstandingMixin,
    QuestionsMixin,
    BasisMixin,
    InsightsMixin,
    SuggestionsMixin,
    ChatFactsMixin,
):
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
        self._clear_caches()
        self.translator = InsightTranslator(llm or create_llm_client(settings), ToolDispatcher(self))

    def _clear_caches(self) -> None:
        """Results worked out once per forecast run. Run ids start again at 1 after a reset, so a new
        business must never meet the old one's results: reset() clears them too."""
        self._backtests: dict = {}  # backtest error per history (roadmap 2.8)
        self._messages: dict[str, str] = {}  # drafted messages per facts (roadmap 3.2)
        self._fixes_cache: dict = {}  # suggested fixes for the latest forecast run (roadmap 3.3)
        self._pay_cache: dict = {}  # safe owner's pay for the latest forecast run (roadmap 3.4)
        self._stress_cache: dict = {}  # stress tests for the latest forecast run (roadmap 3.5)
        self._pairs_cache: dict = {}  # which found payments the owner's own items stand in for
        self._financing_cache: dict = {}  # financing comparison per run and options (roadmap 3.6)
        self._insights_cache: dict = {}  # things we noticed for the latest forecast run (roadmap 4.1)
        self._cards_cache: dict = {}  # their words and tested actions (roadmap 4.2–4.3)
        self._charts_cache: dict = {}  # the Insights page's charts (roadmap 4.3)

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
        insights = self.insights()
        detected += alert_rules.charge_alerts(insights, self.today)  # roadmap R.1
        for found in detected:  # roadmap R.3b: a customer paying later, whose money now lands after the low
            if found.type in ("shortfall", "watch"):
                late = alert_rules.late_customer(insights, found.risk_date, self.today)
                if late:
                    found.facts["late_customer"] = {
                        **late,
                        "customer": templates.payee_name(late["customer"]),
                    }
        open_alerts = self.repo.unresolved_alerts(business.id)  # dismissed ones too, so they stay dismissed
        summary = DailyRunSummary(ran=True, forecast=forecast)
        still_there = set()
        for facts in detected:
            for key in ("top_outflows", "expected_inflows_before"):
                if key in facts.facts:
                    facts.facts[key] = self._plain_names(facts.facts[key])
            if "payee" in facts.facts:
                facts.facts["payee"] = templates.payee_name(facts.facts["payee"])
            text = self.translator.write_alert(facts.facts)
            text.actions = self._actions_for(facts.facts, forecast)
            duplicate = alert_rules.find_duplicate(open_alerts, facts)
            if duplicate:
                still_there.add(duplicate.id)
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
        for alert in open_alerts:  # what today's check no longer finds is solved
            if alert.id not in still_there:
                self.repo.resolve_alert(alert.id)
                summary.alerts_resolved += 1
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
        if next_payment:  # by what it is, not the bank's wording ("Payroll", not "Pago nomina")
            name = self._plain_names([{"label": next_payment[2]}])[0]["label"]
            next_payment = (next_payment[0], next_payment[1], name)
        low_date = forecast.lowest_with_today()[1] if forecast else None
        return Dashboard(
            business=business,
            balance=balance,
            forecast=forecast,
            history=history,
            alerts=self.repo.list_alerts(business.id),
            next_payment=next_payment,
            open_alerts=self.repo.open_alert_count(business.id),
            scheduled=forecast.scheduled if forecast else [],
            lowest_weeks=alert_rules.weeks_until(self.today, low_date) if low_date else None,
            chance_pct=chance_pct(forecast.chance_below(business.low_cash_line)) if forecast else None,
        )

    # ---------------------------------------------------------------- alerts
    def get_alerts(self, open_only: bool = True) -> list[Alert]:
        return self.repo.list_alerts(self._business().id, open_only=open_only)

    def open_alert_count(self) -> int:
        """The sidebar badge: alerts stay counted until they are dismissed or solved, not just seen."""
        business = self.repo.get_business()
        return self.repo.open_alert_count(business.id) if business else 0

    def dismiss_alert(self, alert_id: int) -> None:
        self.repo.dismiss_alert(alert_id)

    def dismissed_alerts(self) -> list[Alert]:
        """Dismissed but not solved: the pages don't say "cash looks healthy" while there are any (R.1)."""
        business = self.repo.get_business()
        return self.repo.dismissed_alerts(business.id) if business else []

    def bring_back_alerts(self) -> None:
        self.repo.bring_back_alerts(self._business().id)

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
        adjustments, name, picked = self._next_month_day(adjustments, name)
        result = self._scenario(adjustments, name)
        result.picked = picked
        result.scenario_id = self.repo.save_scenario(
            self._business().id, name, adjustments, result.summary(), False
        )
        return result

    def _next_month_day(self, adjustments: list[dict], name: str) -> tuple[list[dict], str, dict | None]:
        """Issue 20: a move "to next month" without a day (new_date = NEXT_MONTH) is tried on every
        weekday of next month, and the best day kept (`alert_actions.pick_day`). Only the first such
        move is searched; the chat sends one at a time."""
        index = next(
            (i for i, a in enumerate(adjustments) if a.get("new_date") == NEXT_MONTH),
            None,
        )
        if index is None:
            return adjustments, name, None
        first = (self.today.replace(day=1) + timedelta(days=32)).replace(day=1)
        days = [
            first + timedelta(days=n)
            for n in range((end_of_next_month(self.today) - first).days + 1)
            if (first + timedelta(days=n)).weekday() < 5
        ]
        baseline = self._baseline_forecast()
        line = self._business().low_cash_line
        tried = []
        for day in days:
            trial = [dict(a) for a in adjustments]
            trial[index]["new_date"] = day.isoformat()
            forecast = self._scenario(trial, name, baseline=baseline).scenario
            tried.append((day, forecast.risk_level(line), forecast.lowest.balance_p50))
        day, why = alert_actions.pick_day(tried)
        chosen = [dict(a) for a in adjustments]
        chosen[index]["new_date"] = day.isoformat()
        label = chosen[index].get("label", "")
        picked = {"label": label, "day": day.isoformat(), "why": why, "days_tried": len(days)}
        if adjustments[index].get("type") == "move_item":
            name = f"Move {label} to {day:%b} {day.day}"
        return chosen, name, picked

    def _scenario(
        self, adjustments: list[dict], name: str = "Scenario", baseline: ForecastResult | None = None
    ) -> ScenarioResult:
        """A what-if without keeping it in the owner's history (used to measure actions, roadmap 3.2)."""
        business = self._business()
        parsed = [parse_adjustment(a) for a in adjustments]
        if not parsed:
            raise ValueError("A scenario needs at least one adjustment")
        items = self.repo.list_scheduled_items(business.id)
        try:
            adjusted = apply_adjustments(
                items, parsed, self.today, self.settings.horizon_days, self.weekly_sales()
            )
        except ValueError as exc:
            raise ValueError(self._in_normal_week(parsed) or str(exc)) from exc
        baseline = baseline or self._baseline_forecast()
        scenario = self._forecast_for(adjusted)
        return ScenarioResult(name, parsed, baseline, scenario, business.low_cash_line)

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
        # a what-if's own lines (a purchase, a price change, borrowing) become part of the plan; like
        # the what-if they came from, they never stand in for a payment found in the statement
        items = [replace(i, source="plan") if i.source == "scenario" else i for i in items]
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
        self._clear_caches()

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
        """Each dated payment once, next to the plan item it came from. A payment the owner told us
        about that is also one the statement shows (the quarterly flour order) stands in for it."""
        end = end or self.today + timedelta(days=self.settings.horizon_days - 1)
        # a what-if's own lines (a surprise bill, "sales 20% lower") are never "the same money" as a
        # payment found in the statement: only the owner's real plan items may replace one (3.5)
        trying = [i for i in items if i.source in NEVER_PAIRED]
        events = [
            (when, amount, label, item, (item.id, k))
            for item in items
            if item.source not in NEVER_PAIRED
            for k, (when, amount, label) in enumerate(expand_scheduled_items([item], self.today, end))
        ]
        # pairs found in the saved plan hold when a what-if moves one side; new ones are found too
        replaced, standing_in = self._saved_pairs(end)
        found, _ = self._pairs(items, end, replaced, standing_in)
        dropped = replaced | found
        kept = [
            (when, amount, label, item)
            for when, amount, label, item, key in events
            if not (_from_statement(item) and key in dropped)
        ]
        kept += [
            (when, amount, label, item)
            for item in trying
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
            for when, amount, label, item in sorted(kept, key=lambda e: (e[0], e[1], e[2]))
        ]

    def _pairs(
        self, items: list[ScheduledItem], end: date, taken: set = frozenset(), used: set = frozenset()
    ) -> tuple[set, set]:
        """Which statement occurrences (item id, n-th time) the owner's payments stand in for, and
        which owner occurrences do the standing in; `taken`/`used` are already paired. A one-off the
        owner told us about counts at the day it was first due, wherever it has been moved since, so
        moving it moves the money (a what-if, a saved plan, How we built it)."""
        candidates = []
        for item in items:
            if item.source in NEVER_PAIRED:
                continue
            if not _from_statement(item) and not item.recurrence and item.first_due is not None:
                if self.today <= item.first_due <= end and (item.id, 0) not in used:
                    candidates.append((item.first_due, item.amount, item.label, False, (item.id, 0)))
                continue
            for k, (when, amount, label) in enumerate(expand_scheduled_items([item], self.today, end)):
                key = (item.id, k)
                if key not in taken and key not in used:
                    candidates.append((when, amount, label, _from_statement(item), key))
        pairs = recurring.pair_duplicates(candidates)
        return {candidates[d][4] for d in pairs}, {candidates[k][4] for k in pairs.values()}

    def _saved_pairs(self, end: date) -> tuple[set, set]:
        """The pairs in the saved plan (cached per plan)."""
        stored = self.repo.list_scheduled_items(self._business().id)
        key = (
            self.today,
            end,
            tuple(
                (i.id, i.due_date, i.first_due, i.amount, i.recurrence, i.active, i.paused, i.end_date)
                for i in stored
            ),
        )
        if self._pairs_cache.get("key") != key:
            self._pairs_cache = {"key": key, "pairs": self._pairs(stored, end)}
        return self._pairs_cache["pairs"]

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
