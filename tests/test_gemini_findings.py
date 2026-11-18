"""What the first run of the chat test set on Gemini found (roadmap 5.4, DECISIONS #59): a payment
looked up by name, tool errors the model can correct, month totals for "this month vs last",
and three prompt rules (the question's language, answer as asked, say what was proposed)."""

from __future__ import annotations

from datetime import date

import pytest

from aheadly.ai.prompts import CHAT_SYSTEM_PROMPT
from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
from aheadly.ai.tools import ToolDispatcher
from aheadly.domain import ChatAnswer, ScheduledItem
from tests.chat_eval import business_core, looks_spanish, problems


@pytest.fixture(scope="module")
def garage():
    return business_core("taller-los-pistones")


@pytest.fixture(scope="module")
def costume():
    return business_core("disfraces-la-fantasia")


def test_a_payment_is_found_by_name(garage):
    """The Oct 27 charge is older than the newest 50 lines: only a search finds it."""
    found = ToolDispatcher(garage).dispatch("get_transactions", {"search": "mktplace*zx81"})
    assert [(t["date"], t["amount"]) for t in found["transactions"]] == [("2026-10-27", -689)]
    assert ToolDispatcher(garage).dispatch("get_transactions", {"search": "no such payee"}) == {
        "transactions": []
    }


@pytest.mark.parametrize(
    "raw, missing",
    [
        ({"type": "move_item", "label": "New oven"}, "new_date"),
        ({"type": "collect_early", "label": "Christmas order"}, "new_date"),
        ({"type": "recurring_change", "label": "Rent"}, "amount_delta"),
        ({"type": "revenue_change"}, "percent"),
        ({"type": "one_time_expense"}, "amount"),
    ],
)
def test_a_missing_field_is_named_in_words(raw, missing):
    with pytest.raises(ValueError) as caught:
        parse_adjustment(raw)
    assert missing in str(caught.value) and "needs" in str(caught.value)


def test_an_unknown_payment_lists_the_real_names():
    items = [
        ScheduledItem("Insurance claims (Aseguradora Ejemplo)", 900.0, date(2026, 11, 20)),
        ScheduledItem("Pago arriendo bodega", -1200.0, date(2026, 12, 1)),
    ]
    adj = parse_adjustment({"type": "move_item", "label": "Insurer", "new_date": "2026-12-04"})
    with pytest.raises(ValueError) as caught:
        apply_adjustments(items, [adj], date(2026, 11, 11))
    message = str(caught.value)
    assert "Insurance claims (Aseguradora Ejemplo)" in message and "Pago arriendo bodega" in message


def test_the_tool_error_reaches_the_model_with_the_names(garage):
    out = ToolDispatcher(garage).dispatch(
        "run_scenario",
        {"name": "x", "adjustments": [{"type": "move_item", "label": "Insurer", "new_date": "2026-12-04"}]},
    )
    assert "Insurance claims (Aseguradora Ejemplo)" in out["error"]


def test_cash_summary_has_each_month(costume):
    """'Will November be as good as October?': complete months and this month so far."""
    summary = ToolDispatcher(costume).dispatch("get_cash_summary", {})
    months = {m["month"]: m for m in summary["months"]}
    assert "Oct 2026" in months and set(months["Oct 2026"]) == {"month", "money_in", "money_out", "left"}
    assert months["Oct 2026"]["money_in"] > 0
    so_far = summary["this_month_so_far"]
    assert so_far["month"] == "Nov 2026" and so_far["money_in"] >= 0
    assert "money_in_30d" in summary  # the old fields stay


def test_prompt_rules_from_the_gemini_run():
    prompt = CHAT_SYSTEM_PROMPT.lower()
    assert "same language" in prompt and "spanish payment names" in prompt
    assert "answer the question as asked" in prompt
    assert "say what you proposed" in prompt
    assert "search" in prompt  # a payment by name


def test_the_language_check():
    assert looks_spanish("No, tu saldo bajará de tu línea mínima de $2,000 en diciembre.")
    assert looks_spanish("¿Cuánto costaría la nevera y qué día la comprarías?")
    assert not looks_spanish("Right now, your safe-to-spend amount is $0 because a bad month could dip.")
    item = {
        "question": "¿Cuánto puedo gastar?",
        "lang": "es",
        "tools": [],
        "must_include": [],
        "must_not_include": [],
    }
    assert any("Spanish" in p for p in problems(item, ChatAnswer("You can spend nothing today.", [])))
    assert problems(item, ChatAnswer("Hoy no puedes gastar nada.", [])) == []
    # the second Gemini run: English questions about Spanish payment names got Spanish answers
    english = {**item, "question": "Is my biggest customer paying later?", "lang": "en"}
    late = "Sí, tu cliente más grande está pagando más tarde. Constructora Ejemplo Andina Sas no ha pagado."
    assert "asked in English, answered in Spanish" in problems(english, ChatAnswer(late, []))
    assert (
        problems(
            english, ChatAnswer("Yes: Constructora Ejemplo Andina Sas is paying you later than before.", [])
        )
        == []
    )


def test_one_of_several_words_is_enough():
    item = {
        "question": "What if I buy a new fridge?",
        "tools": [],
        "must_include": [["how much", "price", "cost"]],
        "must_not_include": [],
    }
    assert problems(item, ChatAnswer("What is the price of the fridge and when are you buying it?", [])) == []
    assert problems(item, ChatAnswer("When are you buying it?", [])) == [
        "missing one of ['how much', 'price', 'cost']"
    ]
