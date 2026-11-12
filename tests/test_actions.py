"""Roadmap 3.2: actions that name the real payment and show what they change.

A shortfall alert's actions are worked out by code: which payment in the tight week could move a
little later, which money coming in after it could be asked for a little earlier. Each one is run
through the same what-if as the owner's own (without saving it in their history), so its effect on
the lowest balance, the status and the chance of dipping below the line are real numbers. The
model writes only words: the alert's body and, when the owner asks, a message to send.
"""

import json
from datetime import date, timedelta

from aheadly.ai.guardrails import check_numbers
from aheadly.ai.insight_translator import InsightTranslator
from aheadly.ai.llm_client import LLMReply
from aheadly.ai import templates
from tests.conftest import TODAY


def _shortfall(core):
    core.run_daily_check(force=True)
    return next(a for a in core.get_alerts() if a.type == "shortfall")


def test_actions_name_real_payments_and_carry_their_effect(connected_core):
    alert = _shortfall(connected_core)
    labels = {i.label for i in connected_core.repo.list_scheduled_items(connected_core.status().business.id)}
    tested = [a for a in alert.actions if a.get("adjustment")]
    assert 2 <= len(alert.actions) <= 3 and tested
    for action in tested:
        assert action["adjustment"]["label"] in labels
        assert action["adjustment"]["label"] in action["label"]
        impact = action["impact"]
        assert impact["lowest_after"] > impact["lowest_before"]  # only actions that help are offered
        assert set(impact) >= {"risk_before", "risk_after", "chance_before", "chance_after"}


def test_effect_is_the_same_as_testing_it(connected_core):
    action = next(a for a in _shortfall(connected_core).actions if a.get("adjustment"))
    result = connected_core.run_what_if([action["adjustment"]])
    numbers = result.summary()
    assert action["impact"]["lowest_after"] == numbers["scenario"]["lowest_base_case"]
    assert action["impact"]["lowest_before"] == numbers["baseline"]["lowest_base_case"]
    assert action["impact"]["chance_after"] == numbers["scenario"]["chance_below_line_pct"]


def test_working_out_actions_does_not_fill_the_owners_history(connected_core):
    _shortfall(connected_core)
    assert connected_core.saved_scenarios() == []


def test_best_action_first(connected_core):
    actions = [a for a in _shortfall(connected_core).actions if a.get("adjustment")]
    order = {"safe": 0, "watch": 1, "act_now": 2}
    keys = [(order[a["impact"]["risk_after"]], -a["impact"]["lowest_after"]) for a in actions]
    assert keys == sorted(keys)


def test_regular_payments_are_never_moved(connected_core):
    """Payroll, rent and anything else that comes every week or month is not a "move it once"
    action (moving one moves them all): only a payment that lands once in the next 8 weeks moves."""
    from aheadly.ai.forecast_engine import expand_scheduled_items

    business = connected_core.status().business
    items = {i.label: i for i in connected_core.repo.list_scheduled_items(business.id)}
    end = TODAY + timedelta(days=connected_core.settings.horizon_days)
    for action in _shortfall(connected_core).actions:
        if action.get("adjustment"):
            item = items[action["adjustment"]["label"]]
            assert len(expand_scheduled_items([item], TODAY, end)) == 1


def test_every_action_says_how(connected_core):
    for action in _shortfall(connected_core).actions:
        assert 2 <= len(action["how_to"]) <= 3


def test_draft_message_offline_names_the_payment_and_dates(connected_core):
    alert = _shortfall(connected_core)
    index, action = next((i, a) for i, a in enumerate(alert.actions) if a.get("adjustment"))
    message = connected_core.draft_message(alert.id, index)
    assert action["adjustment"]["label"] in message
    new = date.fromisoformat(action["adjustment"]["new_date"])
    assert f"{new:%b} {new.day}" in message


class _Model:
    name = "fake"

    def __init__(self, text: str):
        self.text = text

    def chat(self, messages, tools=None):
        return LLMReply(content=json.dumps({"message": self.text}))


FACTS = {
    "kind": "move_payment",
    "payee": "Quarterly flour order",
    "amount": 4000,
    "date": "2026-12-15",
    "new_date": "2026-12-22",
    "business": "Panadería La Esquina",
    "owner": "María",
}


def test_model_message_is_checked_like_any_number():
    good = "Hi! Could we move the Quarterly flour order of $4,000 from Dec 15 to Dec 22? Thank you!"
    assert InsightTranslator(_Model(good), tools=None).draft_message(FACTS) == good
    made_up = "Hi! Could we move the $4,500 flour order to Dec 22? Thank you!"
    fallback = InsightTranslator(_Model(made_up), tools=None).draft_message(FACTS)
    assert fallback == templates.message_text(FACTS)
    assert check_numbers(fallback, [FACTS]).passed


def test_messages_for_both_kinds():
    early = {**FACTS, "kind": "collect_early", "payee": "Café Azul", "amount": 5500, "date": "2026-12-24"}
    for facts in (FACTS, early):
        text = templates.message_text(facts)
        assert facts["payee"] in text and "$" in text and "María" in text
        assert check_numbers(text, [facts]).passed
    assert "earlier" in templates.message_text(early)


def test_no_owner_name_still_reads_well():
    text = templates.message_text({**FACTS, "owner": ""})
    assert "This is  " not in text and "Panadería La Esquina" in text


def test_message_is_asked_for_once(connected_core):
    """Drafting calls the model when the owner asks, not when the alert is written, and only once."""
    alert = _shortfall(connected_core)
    index = next(i for i, a in enumerate(alert.actions) if a.get("adjustment"))
    calls = []
    original = connected_core.translator.draft_message
    connected_core.translator.draft_message = lambda facts: calls.append(facts) or original(facts)
    first = connected_core.draft_message(alert.id, index)
    assert connected_core.draft_message(alert.id, index) == first
    assert len(calls) == 1


def test_model_writes_only_the_body():
    from aheadly.ai import prompts

    assert '"actions"' not in prompts.ALERT_INSTRUCTIONS


def test_exact_name_wins_when_one_name_contains_another():
    from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
    from aheadly.domain import ScheduledItem

    items = [
        ScheduledItem("Inventory restock", -900, TODAY + timedelta(days=5)),
        ScheduledItem("Inventory", -1200, TODAY + timedelta(days=6)),
    ]
    later = (TODAY + timedelta(days=20)).isoformat()
    moved = apply_adjustments(
        items, [parse_adjustment({"type": "move_item", "label": "Inventory", "new_date": later})], TODAY
    )
    assert [i.due_date.isoformat() for i in moved] == [(TODAY + timedelta(days=5)).isoformat(), later]
