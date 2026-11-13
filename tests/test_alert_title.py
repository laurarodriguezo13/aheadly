"""The alert's title is chosen by code from the facts, not by the model (live check after the merge, 2026-11-12).

With Gemini on, the bakery's alert said "Heads up: you may run low on cash" while its balance went to -$748,
and the body wrote "$-748". The title states how serious things are, so it follows the numbers like any number.
"""

import json

from aheadly.ai.insight_translator import InsightTranslator
from aheadly.ai.llm_client import LLMReply
from aheadly.ai.templates import alert_title

SHORTFALL = {
    "type": "shortfall",
    "lowest_balance": -748,
    "weeks_ahead": 5,
    "low_cash_line": 2000,
    "top_outflows": [{"label": "Quarterly flour order", "amount": 4000, "date": "2026-12-15"}],
}


class _Model:
    name = "fake"

    def __init__(self, reply: dict):
        self.reply = reply

    def chat(self, messages, tools=None):
        return LLMReply(content=json.dumps(self.reply))


def _write(reply: dict, facts: dict = SHORTFALL):
    return InsightTranslator(_Model(reply), tools=None).write_alert(facts)


def test_title_follows_the_numbers():
    assert alert_title(SHORTFALL) == "Warning: your cash could run out"
    assert alert_title({**SHORTFALL, "lowest_balance": 1200}) == "Heads up: you may run low on cash"
    assert alert_title({"type": "idle_cash"}) == "Good news: you have cash to spare"


def test_model_title_is_replaced_by_the_one_from_the_numbers():
    text = _write(
        {
            "title": "Heads up: you may run low on cash",
            "body": "Your balance might dip to $-748 by Dec 15 because of the Quarterly flour order ($4,000).",
            "actions": [{"label": "Delay a purchase", "detail": "Move it a few weeks."}],
        }
    )
    assert text.title == "Warning: your cash could run out"


def test_negative_money_is_written_minus_first():
    text = _write(
        {
            "body": "Your balance might dip to $-748 by Dec 15 because of the Quarterly flour order ($4,000).",
            "actions": [{"label": "Delay a purchase", "detail": "Move it a few weeks."}],
        }
    )
    assert "-$748" in text.body and "$-748" not in text.body
    assert text.title == "Warning: your cash could run out"  # a reply without a title still gets one


def test_prompt_no_longer_asks_the_model_for_a_title():
    from aheadly.ai import prompts

    assert "Heads up" not in prompts.ALERT_INSTRUCTIONS
    assert '"title"' not in prompts.ALERT_INSTRUCTIONS
