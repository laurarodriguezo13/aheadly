"""Second practice run (ClimaSam on Miguel's app with Prophet and Gemini, 2026-11-18): what it found."""

import json
from datetime import date

from aheadly.ai import recurring
from aheadly.ai.categorizer import by_keywords
from aheadly.ai.insight_translator import InsightTranslator
from aheadly.ai.llm_client import LLMReply


def test_the_owners_words_beat_a_guess_left_in_the_list(connected_core):
    """'My accountant's monthly fee' was saved as the AI's guess, Payroll, still in the list."""
    payee = "TRANSF 0045 REF 88213"
    said = "My accountant's monthly fee"
    assert connected_core.answer_mystery(payee, "payroll", said, guess="payroll") == "other"
    assert connected_core.answer_mystery(payee, "rent", said, guess="payroll") == "rent"  # picked on purpose


PAY_DAYS = """2025-11-17 2025-12-01 2025-12-16 2026-01-02 2026-01-16 2026-01-20:2000 2026-02-02 2026-02-18
2026-03-02 2026-03-16 2026-04-01 2026-04-16 2026-04-17:4000 2026-05-04 2026-05-18 2026-06-01 2026-06-16
2026-07-01 2026-07-16 2026-08-03 2026-08-17 2026-09-01 2026-09-16 2026-10-01 2026-10-16 2026-11-02
2026-11-16""".split()


def test_a_rhythm_with_a_few_extras_is_still_found():
    """ClimaSam's owner pay: $1,800 on the 1st and 16th (or the next business day), plus $2,000 once
    in January and $4,000 in April. Not found at all before, so the safe pay stayed '?'."""
    lines = []
    for n, entry in enumerate(PAY_DAYS):
        day, _, amount = entry.partition(":")
        lines.append(
            recurring.TxLine(
                n,
                date.fromisoformat(day),
                -float(amount or 1800),
                "ACH ENVIADO BANISTMO EDWIN SAMANIEGO",
                "owner_pay",
                False,
            )
        )
    found = recurring.detect(lines, date(2026, 11, 17))
    assert len(found) == 1 and found[0].cadence == "twice a month" and found[0].amount == -1800
    april = PAY_DAYS.index("2026-04-17:4000")
    assert april not in found[0].transaction_ids  # the big extra stays in the normal history


def test_panamas_account_fee_is_a_bank_fee():
    assert by_keywords("CARGO POR MANEJO DE CUENTA", -10) == "bank_fees"


class _Counting:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        return LLMReply(content=json.dumps({"title": "x", "body": "Your cash may fall to $500."}))


def test_an_alert_is_written_once_per_facts():
    """Every answer reran the daily check and asked the model again for the same alert."""
    model = _Counting()
    translator = InsightTranslator(model, tools=None)
    facts = {
        "type": "shortfall",
        "lowest_balance": 500,
        "weeks_ahead": 3,
        "low_cash_line": 2000,
        "top_outflows": [{"label": "Rent", "amount": 1650, "date": "2026-12-02"}],
    }
    first = translator.write_alert(facts)
    assert translator.write_alert(dict(facts)).body == first.body and model.calls == 1
    translator.write_alert({**facts, "lowest_balance": 400})
    assert model.calls == 2
