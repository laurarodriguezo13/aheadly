"""Suggestions, safe to spend, bad surprises and financing (3.2-3.7, R.3)."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta


from aheadly.ai import recurring
from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
from aheadly.ai import templates
from aheadly.core import actions as alert_actions
from aheadly.core import financing
from aheadly.core import safe, stress
from aheadly.domain import (
    ForecastResult,
    ScenarioResult,
)

from aheadly.core.areas.shared import (
    DailyRunSummary,
    DECLINE_REASONS,
)

logger = logging.getLogger(__name__)


class SuggestionsMixin:
    """Part of `AppCore` (issue 14): suggestions, safe to spend, bad surprises and financing (3.2-3.7, R.3)."""

    # ------------------------------------------------------------- actions (3.2)
    def _actions_for(self, facts: dict, forecast: ForecastResult) -> list[dict]:
        """2–3 actions for an alert: worked out and measured by code when it can (roadmap 3.2–3.3),
        general advice (without a what-if) to fill up to two, and for idle cash."""
        generic = templates.alert_text(facts)["actions"]
        if facts["type"] not in ("shortfall", "watch"):
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
            declined=self.declined_suggestions(),
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
                    "payment": templates.CATEGORY_WORDS["owner_pay"],  # not the bank's wording
                    "now_per_payment": pay["now"],
                    "safe_per_payment": pay["safe"],
                    "how_often": pay["how_often"],
                }
                if pay
                else None
            ),
        }

    # ------------------------------------------------------- suggestions you can work with (R.3)
    def declined_suggestions(self) -> list[dict]:
        """The owner's "Not for me" answers, as rules the suggestions respect."""
        business = self.repo.get_business()
        return self.repo.get_profile(business.id).get("declined_suggestions", []) if business else []

    def decline_suggestion(self, action: dict, reason: str, note: str = "") -> dict:
        """'Not for me', with a reason. Some reasons rule out a whole kind ("I can't lower my pay"),
        some one payment ("they won't agree"), the rest this suggestion; the alerts and every list
        of suggestions are worked out again without it."""
        kind, payment = action.get("kind"), action.get("payment")
        if reason not in DECLINE_REASONS:
            raise ValueError(f"Unknown reason {reason!r}")
        if reason == "cant_lower_pay":
            rule = {"kind": "owner_pay"}
        elif reason == "cant_raise_prices":
            rule = {"kind": "price"}
        elif payment and kind != "pair":
            rule = {"kind": kind, "label": payment}
        else:
            rule = {"id": action.get("id") or alert_actions.suggestion_id(action["adjustments"])}
        rule |= {"reason": reason, "note": note.strip(), "what": action["label"]}
        rules = [r for r in self.declined_suggestions() if r.get("what") != action["label"]] + [rule]
        self.repo.save_profile(self._business().id, {"declined_suggestions": rules})
        self._suggestions_changed()
        return rule

    def bring_back_suggestions(self) -> None:
        self.repo.save_profile(self._business().id, {"declined_suggestions": []})
        self._suggestions_changed()

    def _suggestions_changed(self) -> None:
        self._fixes_cache, self._cards_cache, self._stress_cache = {}, {}, {}
        self.run_daily_check(force=True)  # the alerts' own suggestions are worked out again

    def all_suggestions(self) -> list[dict]:
        """Every tested suggestion the app has right now, once each, with where it comes from:
        the alerts, the things we noticed and the bad surprises (tested with the surprise in place,
        `context`)."""
        found, seen = [], set()

        def add(action: dict, source: str, context: list[dict] | None = None) -> None:
            if not action.get("adjustments"):
                return
            sid = alert_actions.suggestion_id((context or []) + action["adjustments"])
            if sid not in seen:
                seen.add(sid)
                found.append({"id": sid, "action": action, "source": source, "context": context or []})

        for alert in self.get_alerts():
            for action in alert.actions:
                add(action, alert.title)
        for card in self.noticed_cards():
            for action in card["actions"]:
                add(action, card["title"])
        for test in self.stress_tests():
            for action in test["fixes"]:
                add(action, test["label"], test["adjustments"])
        return found

    def test_suggestion(self, adjustments: list[dict], context: list[dict] | None = None) -> dict:
        """A suggestion as it is or as the owner changed it, tested (with a bad surprise in place
        when it came from one). Not kept in the history."""
        result = self._scenario((context or []) + adjustments, "Your version")
        return {"result": result, "impact": alert_actions.impact(result)}

    def save_suggestion(self, adjustments: list[dict], name: str) -> DailyRunSummary:
        """Save as my plan: only the change itself, never the bad surprise it was tested against."""
        return self.save_plan(self._scenario(adjustments, name))

    def suggestions_for_chat(self) -> dict:
        """The get_suggestions chat tool (roadmap R.3b): how much is missing and by when, every tested
        suggestion with its effect (not the bad surprises': they answer "what if"), and what the
        owner said no to."""
        business = self._business()
        line = business.low_cash_line
        forecast = self._baseline_forecast()
        lowest = forecast.lowest
        data = {
            "low_cash_line": round(line),
            "lowest_balance": round(lowest.balance_p50),
            "lowest_date": lowest.date.isoformat(),
            "suggestions": [
                {
                    "label": entry["action"]["label"],
                    "from": entry["source"],
                    "lowest_before": entry["action"]["impact"]["lowest_before"],
                    "lowest_after": entry["action"]["impact"]["lowest_after"],
                    "worst_before": entry["action"]["impact"]["worst_before"],
                    "worst_after": entry["action"]["impact"]["worst_after"],
                    "status_before": entry["action"]["impact"]["risk_before"],
                    "status_after": entry["action"]["impact"]["risk_after"],
                    "chance_before": entry["action"]["impact"]["chance_before"],
                    "chance_after": entry["action"]["impact"]["chance_after"],
                }
                for entry in self.all_suggestions()
                if not entry["context"]
            ][:5],
            "said_no_to": [rule["what"] for rule in self.declined_suggestions()],
        }
        if lowest.balance_p50 < line:
            data["short_by"] = round(line - lowest.balance_p50)
        still = self.still_short()
        if still:
            data["still_short_after_best"] = still
        return data

    def stress_tests(self) -> list[dict]:
        """Four bad surprises from the business's own numbers: what each does, whether the base case
        stays above the line ("fine") or how much is missing ("short"), and what would help.
        Not kept in the owner's history; worked out once per forecast run."""
        business = self._business()
        run = self.repo.latest_forecast(business.id)
        key = (run.run_id if run else None, business.low_cash_line)
        if self._stress_cache.get("key") == key:
            return self._stress_cache["tests"]
        line = business.low_cash_line
        items = self.repo.list_scheduled_items(business.id)
        end = self.today + timedelta(days=self.settings.horizon_days - 1)
        baseline = self._baseline_forecast()
        weekly = self.weekly_sales()
        tests = []
        replaced, _ = self._saved_pairs(end)
        for surprise in stress.surprises(
            items, self.today, end, weekly, self._avg_monthly_outflow(), replaced
        ):
            result = self._scenario(surprise["adjustments"], surprise["label"], baseline=baseline)
            impact = alert_actions.impact(result)
            short = impact["lowest_after"] < line
            fixes = []
            if short:
                stressed = apply_adjustments(
                    items,
                    [parse_adjustment(a) for a in surprise["adjustments"]],
                    self.today,
                    self.settings.horizon_days,
                    weekly,
                )
                fixes = alert_actions.build(
                    result.scenario,
                    line,
                    stressed,
                    self.today,
                    end,
                    lambda adjs, s=surprise, f=result.scenario: self._scenario(
                        s["adjustments"] + adjs, "Stress fix", baseline=f
                    ),
                    weekly,
                    frozenset(a["label"] for a in surprise["adjustments"] if "label" in a),
                    declined=self.declined_suggestions(),
                )[:2]
            tests.append(
                {
                    **surprise,
                    "impact": impact,
                    "verdict": "short" if short else "fine",
                    "low_cash_line": line,
                    "gap": round(line - impact["lowest_after"]) if short else None,
                    "fixes": fixes,
                }
            )
        self._stress_cache = {"key": key, "tests": tests}
        return tests

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

    def stress_result(self, key: str) -> ScenarioResult:
        """One stress test's full what-if, for its chart; not saved in the owner's history."""
        test = next(t for t in self.stress_tests() if t["key"] == key)
        return self._scenario(test["adjustments"], test["label"])

    # -------------------------------------------------------------- financing helper (3.6)
    def test_loan(
        self, amount: float, yearly_rate: float, months: int, fees: float = 0.0, start: date | None = None
    ) -> dict:
        """Roadmap R.2: a loan the owner is thinking about, on their own numbers (no lender, no offer).
        The monthly payment and what it costs come from code; the what-if shows what it does to the
        next 8 weeks. Not kept in the history until the owner saves it as the plan."""
        start = start or self.today
        if start < self.today:
            raise ValueError("The money can't come in before today.")
        adjustment = {
            "type": "loan",
            "amount": amount,
            "yearly_rate": yearly_rate,
            "months": months,
            "fees": fees,
            "start_date": start.isoformat(),
            "label": f"Loan of ${amount:,.0f}",
        }
        result = self._scenario([adjustment], f"Loan of ${amount:,.0f} over {months} months")
        schedule = financing.loan_payments(amount, yearly_rate, months, start)
        end = self.today + timedelta(days=self.settings.horizon_days - 1)
        in_window = [pay for when, pay in schedule if when <= end]
        line = result.low_cash_line
        paid = round(sum(pay for _, pay in schedule), 2)
        return {
            "result": result,
            "monthly_payment": financing.monthly_payment(amount, yearly_rate, months),
            "payments": len(schedule),
            "last_payment": schedule[-1][0],
            "interest": round(paid - amount, 2),
            "total_cost": round(paid - amount + fees, 2),
            "payments_in_window": len(in_window),
            "paid_in_window": round(sum(in_window), 2),
            "lowest_before": round(result.baseline.lowest.balance_p50),
            "lowest_after": round(result.scenario.lowest.balance_p50),
            "risk_before": result.baseline.risk_level(line),
            "risk_after": result.scenario.risk_level(line),
        }

    def financing_options(self) -> list[dict]:
        """The ways to cover a gap the owner says they have (nothing is offered by the app)."""
        return list(self.repo.get_profile(self._business().id).get("financing_options", []))

    def add_financing_option(self, raw: dict) -> dict:
        option = financing.check_option(raw)
        options = self.financing_options() + [option]
        self.repo.save_profile(self._business().id, {"financing_options": options})
        return option

    def remove_financing_option(self, index: int) -> None:
        options = self.financing_options()
        if 0 <= index < len(options):
            del options[index]
            self.repo.save_profile(self._business().id, {"financing_options": options})

    @staticmethod
    def financing_kinds() -> dict[str, dict]:
        return financing.KINDS

    @staticmethod
    def financing_label(option: dict) -> str:
        """How a saved option reads in the list: its name and the numbers the owner gave."""
        parts = [financing.label(option)]
        if "limit" in option:
            parts.append(f"up to ${option['limit']:,.0f}")
        if option.get("rate"):
            parts.append(f"{option['rate']:g}% a year")
        if option.get("fee"):
            parts.append(f"${option['fee']:,.0f} fees")
        if option.get("extra_days"):
            parts.append(f"{option['extra_days']:g} more days")
        if option.get("fee_pct"):
            parts.append(f"{option['fee_pct']:g}% fee")
        if option.get("arrive_days"):
            parts.append(f"arrives in {option['arrive_days']:g} days")
        return " · ".join(parts)

    def financing_payments(self) -> dict[str, list[str]]:
        """Payments in the forecast's weeks an option can be about: money going out (longer supplier
        terms) and money coming in (getting an invoice paid early)."""
        found = self._horizon_payments()
        return {
            "out": sorted(k for k, (amount, _) in found.items() if amount < 0),
            "in": sorted(k for k, (amount, _) in found.items() if amount > 0),
        }

    def _horizon_payments(self) -> dict[str, tuple[float, date]]:
        end = self.today + timedelta(days=self.settings.horizon_days - 1)
        found: dict[str, tuple[float, date]] = {}
        for when, amount, label in sorted(self._events(end)):
            found.setdefault(label, (amount, when))  # the next one
        return found

    def financing_hint(self) -> dict | None:
        """Money from a loan or credit line in the last year of the statement: the owner may still have
        it (said as a hint; it's only compared once the owner adds it with its rate)."""
        lines = self.repo.list_transactions(self._business().id, limit=100000)
        if lines.empty:
            return None
        since = (self.today - timedelta(days=365)).isoformat()
        drawn = lines[
            (lines["category"] == "loan") & (lines["amount"] > 0) & (lines["date"].astype(str) >= since)
        ]
        if drawn.empty:
            return None
        return {"times": int(len(drawn)), "biggest": round(float(drawn["amount"].max()))}

    def compare_financing(self) -> dict:
        """Timing or structural, how big the gap is, and what each of the owner's own options would
        cost, each tested as a what-if (repayment included). Worked out once per forecast run and
        options; nothing is saved in the owner's history."""
        business = self._business()
        line = business.low_cash_line
        options = self.financing_options()
        run = self.repo.latest_forecast(business.id)
        key = (run.run_id if run else None, line, json.dumps(options, sort_keys=True))
        if self._financing_cache.get("key") == key:
            return self._financing_cache["result"]
        baseline = self._baseline_forecast()
        g = financing.gap(baseline, line)
        items = self.repo.list_scheduled_items(business.id)
        one_offs = sum(e.amount for e, item in self._dated_events(items) if not item.recurrence)
        weeks = self.settings.horizon_days // 7
        normal = financing.regular_weekly(
            self.repo.current_balance(business.id), baseline.points[-1].balance_p50, one_offs, weeks
        )
        verdict = financing.verdict(g, normal)
        plans = []
        if verdict == "timing":
            need = financing.amount_needed(g)
            payments = self._horizon_payments()
            for option in options:
                p = financing.plan(option, need, g, baseline, line, self.today, payments)
                if p["adjustments"]:
                    result = self._scenario(p["adjustments"], p["label"], baseline=baseline)
                    i = alert_actions.impact(result)
                    i["covers"] = (i["lowest_after"] if g["base_dips"] else i["worst_after"]) >= line
                    p["impact"] = i
                plans.append(p)
            plans.sort(key=financing.rank_key)
        actions = [
            {
                **templates.financing_words(p),
                "kind": "financing",
                "adjustments": p["adjustments"],
                "impact": p["impact"],
                "cost": p["cost"],
            }
            for p in plans
            if p["feasible"] and p.get("impact", {}).get("covers")
        ][:2]
        result = {
            "verdict": verdict,
            "gap": g,
            "normal_week": normal,
            "weeks": weeks,
            "low_cash_line": line,
            "need": financing.amount_needed(g) if verdict != "none" else 0,
            "options": plans,
            "actions": actions,
            "hint": self.financing_hint(),
        }
        self._financing_cache = {"key": key, "result": result}
        return result

    def financing_summary(self) -> dict:
        """What the chat may say about covering a gap (every number from code)."""
        c = self.compare_financing()
        g = c["gap"]
        return {
            "verdict": c["verdict"],
            "low_cash_line": c["low_cash_line"],
            "base_short": g["base"],
            "worst_short": g["worst"],
            "gap_starts": g["start"].isoformat() if g["start"] else None,
            "recovery": g["recovery"].isoformat() if g["recovery"] else None,
            "normal_week": c["normal_week"],
            "weeks": c["weeks"],
            "amount_to_cover": c["need"],
            "options": [
                {
                    "label": p["label"],
                    "cost": round(p["cost"]),
                    "yearly_rate": p.get("yearly_rate", 0.0),
                    "usable": bool(p["feasible"] and p.get("impact", {}).get("covers")),
                }
                for p in c["options"]
            ],
            "not_advice": True,
        }
