"""Things we noticed, the charts and their summaries (4.1-4.3)."""

from __future__ import annotations

import logging
import math
from datetime import date


from aheadly.ai.forecast_engine import (
    history_balances,
)
from aheadly.ai import templates
from aheadly.core import actions as alert_actions
from aheadly.core import alert_rules, insight_charts, pattern_rules
from aheadly.domain import (
    ForecastResult,
    ScenarioResult,
)

from aheadly.core.areas.shared import (
    INSIGHT_ACTION_KINDS,
)

logger = logging.getLogger(__name__)


class InsightsMixin:
    """Part of `AppCore` (issue 14): things we noticed, the charts and their summaries (4.1-4.3)."""

    # ---------------------------------------------------------- stress tests (3.5)
    # ------------------------------------------------------------- things we noticed (4.1)
    def insights(self) -> list[dict]:
        """Patterns worth knowing even when cash is fine (aheadly/core/pattern_rules.py), plus idle
        cash from the alert rules. Worked out once per forecast run and kept in the insights table."""
        business = self._business()
        run = self.repo.latest_forecast(business.id)
        if run is None:
            return []
        if self._insights_cache.get("key") == run.run_id:
            return self._insights_cache["insights"]
        rows = self.repo.recurring_lines(business.id)
        df = pattern_rules.lines_frame(rows)
        profile = self.repo.get_profile(business.id)
        seasons = {int(m) for m in profile.get("busy_months", []) + profile.get("slow_months", [])}
        found = self.detected_recurring()
        dates = {r[0]: date.fromisoformat(r[1]) for r in rows}
        first = {
            f.match_key: min(dates[i] for i in f.transaction_ids if i in dates)
            for f in found
            if any(i in dates for i in f.transaction_ids)
        }
        insights = [
            i.as_dict()
            for i in pattern_rules.find(
                df, self.today, self.repo.current_balance(business.id), seasons, found, first
            )
        ]
        idle = alert_rules.detect_idle_cash(run, business, self._avg_monthly_outflow(), self.today)
        if idle:
            facts = {k: v for k, v in idle.facts.items() if k != "possible_actions"}
            insights.append(
                {
                    "type": "idle_cash",
                    "severity": "low",
                    "facts": facts,
                    "actions": idle.facts["possible_actions"],
                }
            )
        self.repo.replace_insights(business.id, run.run_id, insights)
        self._insights_cache = {"key": run.run_id, "insights": insights}
        return insights

    def insight_cards(self) -> list[dict]:
        """Each thing we noticed with a title (code), 1–3 sentences (the model, every number checked,
        template if not; roadmap 4.2) and what could help (4.3): the ones the forecast can test (your
        own pay, prices, cancelling a regular charge) run as what-ifs first and carry their effect,
        like an alert's actions. Worked out once per forecast run."""
        insights = self.insights()
        run = self.repo.latest_forecast(self._business().id)
        key = (run.run_id if run else None, self._business().low_cash_line)
        if self._cards_cache.get("key") == key:
            return self._cards_cache["cards"]
        baseline = self._baseline_forecast() if insights else None
        cards = []
        for insight in insights:
            text = self.translator.write_insight(insight)
            cards.append(
                {
                    "type": insight["type"],
                    "severity": insight["severity"],
                    "title": text.title,
                    "body": text.body,
                    "actions": [
                        a for a in (self._insight_action(a, insight, baseline) for a in text.actions) if a
                    ],
                    "facts": insight["facts"],
                    # roadmap R.1: a charge to check and idle cash are alerts too, so the Insights page
                    # and the dashboard leave them out (the chat still sees them)
                    "is_alert": insight["type"] in (*alert_rules.CHARGE_TYPES, "idle_cash"),
                }
            )
        self._cards_cache = {"key": key, "cards": cards}
        return cards

    def _insight_action(self, action: dict, insight: dict, baseline: ForecastResult) -> dict | None:
        """An insight's action, tested on the forecast when it maps to a what-if (roadmap 4.3).
        None when the owner ruled out that kind of change: not even as untested advice (issue 30)."""
        declined = self.declined_suggestions()
        kind = INSIGHT_ACTION_KINDS.get(action["key"])
        if kind and alert_actions.ruled_out([r for r in declined if "label" not in r], kind):
            return None
        items = [i for i in self.repo.list_scheduled_items(self._business().id) if i.active and not i.paused]
        found = None
        if action["key"] == "lower_owner_pay_for_a_while":
            pay = next(
                (i for i in items if i.category == "owner_pay" and i.recurrence and i.amount < 0), None
            )
            if pay:
                name = templates.payment_name(pay.label, pay.category, pay.source == "statement")
                words = templates.action_words("owner_pay", payee=name, amount=-pay.amount, pct=25)
                delta = round(-pay.amount * 0.25, 2)
                found = (
                    words,
                    [
                        {
                            "type": "recurring_change",
                            "label": pay.label,
                            "amount_delta": delta,
                            "start_date": self.today.isoformat(),
                        }
                    ],
                )
        elif action["key"] in ("review_prices", "raise_prices_to_cover"):
            weekly = self.weekly_sales()
            if weekly > 0:
                words = templates.action_words("price", pct=5, weekly=weekly)
                found = (
                    words,
                    [{"type": "revenue_change", "percent": 5, "start_date": self.today.isoformat()}],
                )
        elif action["key"] == "cancel_if_not_needed":
            label = insight["facts"].get("payee")
            item = next((i for i in items if i.label == label and i.recurrence), None)
            if item:
                name = templates.payment_name(item.label, item.category, item.source == "statement")
                words = templates.cancel_words(name, -item.amount, insight["facts"].get("how_often", ""))
                found = (words, [{"type": "remove_item", "label": item.label}])
        if not found:
            return action
        words, adjustments = found
        kind = INSIGHT_ACTION_KINDS[action["key"]]
        payment = adjustments[0].get("label") if kind in ("owner_pay", "cancel") else None
        if alert_actions.ruled_out(declined, kind, payment, alert_actions.suggestion_id(adjustments)):
            return None  # the owner said no to this change (roadmap R.3)
        result = self._scenario(adjustments, words["label"], baseline=baseline)
        effect = alert_actions.impact(result)
        if (
            effect["lowest_after"] <= effect["lowest_before"]
            and effect["worst_after"] <= effect["worst_before"]
            and effect["chance_after"] == effect["chance_before"]
        ):
            return action  # it changes nothing in the next 8 weeks: offer it as advice, untested
        return {
            **words,
            "key": action["key"],
            "kind": kind,
            "adjustments": adjustments,
            "impact": effect,
            "id": alert_actions.suggestion_id(adjustments),
            "payment": payment,
            **({"pay": round(-pay.amount, 2)} if kind == "owner_pay" else {}),
        }

    def noticed_cards(self) -> list[dict]:
        """The things we noticed the Insights page and the dashboard show: not the ones on Alerts,
        nor the ones the owner set aside ("I know about it", "Not right", roadmap R.3)."""
        set_aside = self.repo.get_profile(self._business().id).get("insights_set_aside", {})
        return [
            card for card in self.insight_cards() if not card["is_alert"] and card["type"] not in set_aside
        ]

    def set_aside_insight(self, insight_type: str, reason: str) -> None:
        if reason not in ("known", "wrong"):
            raise ValueError("reason is 'known' or 'wrong'")
        profile = self.repo.get_profile(self._business().id)
        set_aside = {**profile.get("insights_set_aside", {}), insight_type: reason}
        self.repo.save_profile(self._business().id, {"insights_set_aside": set_aside})

    def insights_for_chat(self) -> dict:
        """The get_insights chat tool (roadmap 4.3): what we noticed, with the numbers behind it."""
        return {
            "insights": [
                {
                    "title": card["title"],
                    "body": card["body"],
                    "facts": templates.readable_insight(card),
                }
                for card in self.insight_cards()
            ]
        }

    def insight_charts(self) -> dict:
        """The Insights page's charts (roadmap 4.3), each with its numbers, the facts behind its
        summary and the summary (4.2). Worked out once per forecast run; a chart without enough
        months of statement is left out."""
        business = self._business()
        run = self.repo.latest_forecast(business.id)
        key = run.run_id if run else None
        if self._charts_cache.get("key") == key:
            return self._charts_cache["charts"]
        df = pattern_rules.lines_frame(self.repo.recurring_lines(business.id))
        months = insight_charts.complete_months(df, self.today)
        balance = self.repo.current_balance(business.id)
        in_out = insight_charts.money_in_out(df, months)
        names, spending = insight_charts.spending_by_category(df, months)
        cushion = insight_charts.cushion(df, balance, self.today, months)
        sources = insight_charts.income_sources(df, self.today)
        charts = {
            "money_in_out": {"rows": in_out, "facts": insight_charts.money_in_out_facts(in_out)},
            "spending": {
                "names": names,
                "rows": spending,
                "facts": insight_charts.spending_facts(names, spending),
            },
            "cushion": {"rows": cushion, "facts": insight_charts.cushion_facts(cushion)},
            "income_sources": {"rows": sources, "facts": insight_charts.income_facts(sources)},
        }
        charts = {k: v for k, v in charts.items() if v["facts"]}
        for chart in charts.values():
            chart["summary"] = self.translator.summarize_chart(chart["facts"])
        self._charts_cache = {"key": key, "charts": charts}
        return charts

    def forecast_chart_facts(self) -> dict | None:
        """What the dashboard's chart shows, as numbers (roadmap 4.2)."""
        business = self._business()
        run = self.repo.latest_forecast(business.id)
        if run is None:
            return None
        balance = self.repo.current_balance(business.id)
        history = history_balances(self.repo.daily_net_flow(business.id), balance)
        line = business.low_cash_line
        lowest = run.lowest
        run.scheduled = self._events(run.horizon_end)
        before = run.top_outflows(lowest.date, limit=1)
        return {
            "chart": "forecast",
            "weeks": math.ceil(len(run.points) / 7),
            "balance_weeks_ago": round(history["balance"].iloc[0]) if len(history) >= 28 else None,
            "balance_today": round(balance),
            "lowest_base_case": round(lowest.balance_p50),
            "lowest_date": lowest.date.isoformat(),
            "lowest_worst_case": round(run.min_p10),
            "end_base_case": round(run.points[-1].balance_p50),
            "low_cash_line": round(line),
            "risk_level": run.risk_level(line),
            "chance_below_line_pct": alert_rules.chance_pct(run.chance_below(line)),
            "payment_before_lowest": self._plain_names(before)[0] if before else None,
        }

    def forecast_chart_summary(self) -> str | None:
        facts = self.forecast_chart_facts()
        return self.translator.summarize_chart(facts) if facts else None

    def scenario_chart_summary(self, result: ScenarioResult, what: str = "change") -> str:
        """Under a what-if's chart (Test this, a stress test): with the change (or the surprise)
        against without it."""
        summary = result.summary()
        facts = {
            "chart": "scenario",
            "what": what,
            **{k: summary[k] for k in ("scenario_name", "low_cash_line", "baseline", "scenario")},
        }
        return self.translator.summarize_chart(facts)

    def _plain_names(self, payments: list[dict]) -> list[dict]:
        """Payments found in the statement called by what they are ("Payroll", "Rent") or by the
        payee without the bank's words; the owner's own names stay (live check, 2026-11-13)."""
        items = {i.label: i for i in self.repo.list_scheduled_items(self._business().id)}
        out = []
        for p in payments:
            item = items.get(p["label"])
            name = (
                templates.payment_name(item.label, item.category, item.source == "statement")
                if item
                else p["label"]
            )
            out.append({**p, "label": name})
        return out
