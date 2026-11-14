"""Function-calling tools: schemas the LLM sees and the dispatcher that runs them.

Every tool is a thin call into App Core that returns plain JSON-serialisable
dicts. Errors come back as {"error": ...} so the chat never crashes.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from aheadly.ai.categorizer import CATEGORIES
from aheadly.ai.plan_text import PROPOSE_TOOL

if TYPE_CHECKING:  # avoids a runtime import cycle (App Core builds the dispatcher)
    from aheadly.core.app_core import AppCore

logger = logging.getLogger(__name__)

WEEKS_PARAM = {"type": "integer", "minimum": 1, "maximum": 8, "description": "How many weeks ahead (1 to 8)."}

ADJUSTMENT_SCHEMA = {
    "type": "object",
    "description": "One change to test. Use `type` plus the fields that type needs.",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "one_time_expense",
                "move_item",
                "remove_item",
                "recurring_change",
                "revenue_change",
                "collect_early",
                "financing",
            ],
        },
        "amount": {
            "type": "number",
            "description": "one_time_expense: positive amount of the purchase; financing: amount borrowed",
        },
        "date": {"type": "string", "description": "one_time_expense: ISO date"},
        "label": {
            "type": "string",
            "description": "Name of the scheduled item (e.g. 'oven') or of the new expense",
        },
        "new_date": {"type": "string", "description": "move_item / collect_early: new ISO date"},
        "amount_delta": {"type": "number", "description": "recurring_change: signed change per occurrence"},
        "percent": {"type": "number", "description": "revenue_change: +10 means sales up 10%"},
        "weeks": {
            "type": "integer",
            "description": "revenue_change: how many weeks it lasts (leave out: from then on)",
        },
        "start_date": {
            "type": "string",
            "description": "ISO date the change starts (financing: money comes in)",
        },
        "repay_date": {"type": "string", "description": "financing: ISO date it is paid back"},
        "cost": {"type": "number", "description": "financing: interest and fees in dollars, paid with it"},
    },
    "required": ["type"],
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_cash_summary",
        "description": "Current balance, money in/out over the last 30 days and the low cash line.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_forecast",
        "description": "Weekly worst/base/best balances for the coming weeks and the lowest point.",
        "parameters": {
            "type": "object",
            "properties": {
                "weeks": WEEKS_PARAM,
                "until": {
                    "type": "string",
                    "description": "Optional ISO date: only look up to this day (for 'next month' use the end of next month).",
                },
            },
        },
    },
    {
        "name": "get_upcoming_outflows",
        "description": "Known large payments going out in the coming weeks.",
        "parameters": {"type": "object", "properties": {"weeks": WEEKS_PARAM}},
    },
    {
        "name": "get_transactions",
        "description": "Recent transactions, optionally filtered by category or start date.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(CATEGORIES)},
                "since": {"type": "string", "description": "ISO date"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    },
    {
        "name": "run_scenario",
        "description": "Re-run the forecast with changes (a purchase, moving a payment, a sales change) and compare with the baseline.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short name for the scenario"},
                "adjustments": {"type": "array", "items": ADJUSTMENT_SCHEMA},
            },
            "required": ["name", "adjustments"],
        },
    },
    {
        "name": "get_alerts",
        "description": "Open alerts with the facts behind them.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "compare_financing",
        "description": (
            "Whether a cash gap is about timing (money is coming, just late) or structural (more goes out "
            "than comes in), how big it is, and what each of the owner's own options (credit line, card, "
            "supplier terms, early invoices) would cost, each tested on the forecast. Not financial advice."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "safe_to_spend",
        "description": (
            "How much the owner can spend today, and pay themselves per payment, while even a bad month "
            "stays above the low cash line."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_insights",
        "description": (
            "Things we noticed in the owner's statement even when cash is fine (a thin cushion, a cost "
            "creeping up, one big customer, a customer paying later, doubled or unusual charges, sales "
            "slowing...), each with its title, a short explanation and the numbers behind it."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    PROPOSE_TOOL,
]


class ToolDispatcher:
    def __init__(self, core: "AppCore"):
        self._core = core
        self.last_scenario = None  # the UI renders a result card when a what-if ran
        self.last_proposals: list = []  # plan items the chat proposed (roadmap 2.4); the owner adds them
        self.last_question = ""  # what the owner wrote: proposed amounts must appear in it

    @property
    def schemas(self) -> list[dict]:
        return TOOL_SCHEMAS

    def scheduled_labels(self) -> list[str]:
        """Names of the business's scheduled items (the offline planner uses them when a provider is down)."""
        return self._core.scheduled_labels()

    def dispatch(self, name: str, arguments: dict) -> dict:
        """EAFP: run the tool, turn any failure into an error payload for the model."""
        try:
            result = self._run(name, arguments)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("tool %s failed: %s", name, exc)
            return {"error": str(exc)}
        json.dumps(result)  # fail loudly here if a tool returns something non-serialisable
        return result

    def _run(self, name: str, args: dict) -> dict:
        core = self._core
        if name == "get_cash_summary":
            return core.cash_summary()
        if name == "get_forecast":
            return core.forecast_summary(weeks=int(args.get("weeks", 8)), until=args.get("until"))
        if name == "get_upcoming_outflows":
            return {"outflows": core.upcoming_outflows(weeks=int(args.get("weeks", 8)))}
        if name == "get_transactions":
            return {
                "transactions": core.recent_transactions(
                    args.get("category"), args.get("since"), int(args.get("limit", 10))
                )
            }
        if name == "run_scenario":
            result = core.run_what_if(args.get("adjustments", []), args.get("name", "Scenario"))
            self.last_scenario = result
            return result.summary()
        if name == "get_alerts":
            return {"alerts": core.alerts_as_dicts()}
        if name == "safe_to_spend":
            return core.safe_numbers()
        if name == "compare_financing":
            return core.financing_summary()
        if name == "get_insights":
            return core.insights_for_chat()
        if name == "propose_plan_items":
            proposals = core.check_proposals(args, self.last_question)
            self.last_proposals = proposals
            return {
                "proposed": [p.to_dict() for p in proposals],
                "saved": False,
                "note": "Not saved yet: the owner checks each item and presses Add.",
            }
        raise ValueError(f"Unknown tool '{name}'")
