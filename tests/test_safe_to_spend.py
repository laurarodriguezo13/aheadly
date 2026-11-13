"""Roadmap 3.4: safe to spend and a safe pay for the owner.

Safe to spend now: the biggest one-off payment today that keeps even the worst case (the bad-month
line) at or above the low cash line for the next 8 weeks. Because every scenario drops by the same
amount, the worst case drops by exactly that much, so it is the lowest worst-case balance (or
today's cash, if lower) minus the line, rounded down to $10.

Safe pay for the owner: the biggest amount per payment (instead of today's) that keeps the worst
case at or above the line, found by testing it as a what-if.
"""

from datetime import timedelta

from tests.test_businesses import import_business


def _worst_after(core, adjustments):
    return core.run_what_if(adjustments).scenario.min_p10


def test_spending_exactly_that_keeps_the_worst_case_on_the_line():
    core = import_business("estudio-lapiz-rojo", with_one_offs=True)  # healthy: plenty to spend
    line = core.status().business.low_cash_line
    safe = core.safe_to_spend()
    assert safe["amount"] > 0 and safe["amount"] % 10 == 0
    today = core.today.isoformat()
    assert (
        _worst_after(core, [{"type": "one_time_expense", "amount": safe["amount"], "date": today}])
        >= line - 1
    )
    assert (
        _worst_after(core, [{"type": "one_time_expense", "amount": safe["amount"] + 50, "date": today}])
        < line + 50
    )


def test_nothing_is_safe_when_a_bad_month_already_dips(connected_core):
    safe = connected_core.safe_to_spend()
    assert safe["amount"] == 0 and safe["reason"] == "already_below"


def test_safe_owner_pay_keeps_the_worst_case_on_the_line():
    core = import_business("ferreteria-don-perno", with_one_offs=True)  # watch, owner's pay known
    line = core.status().business.low_cash_line
    pay = core.safe_owner_pay()
    assert pay is not None and pay["now"] > 0 and pay["safe"] % 10 == 0
    assert pay["safe"] < pay["now"]  # today's pay lets a bad month dip below the line
    delta = pay["now"] - pay["safe"]
    change = [
        {
            "type": "recurring_change",
            "label": pay["label"],
            "amount_delta": delta,
            "start_date": core.today.isoformat(),
        }
    ]
    assert _worst_after(core, change) >= line - 1


def test_healthy_business_could_pay_itself_more():
    core = import_business("estudio-lapiz-rojo", with_one_offs=True)
    pay = core.safe_owner_pay()
    if pay is not None:
        assert pay["safe"] >= pay["now"]


def test_no_owner_pay_known_means_no_answer(connected_core):
    assert connected_core.safe_owner_pay() is None


def test_chat_answers_how_much_is_safe_to_spend():
    core = import_business("estudio-lapiz-rojo", with_one_offs=True)
    answer = core.ask("How much can I spend safely this week?")
    assert "safe_to_spend" in answer.tool_names
    amount = core.safe_to_spend()["amount"]
    assert f"${amount:,}" in answer.text


def test_tool_numbers_include_both_answers():
    core = import_business("ferreteria-don-perno", with_one_offs=True)
    numbers = core.safe_numbers()
    assert set(numbers) >= {"safe_to_spend_now", "low_cash_line", "lowest_worst_case", "owner_pay"}
    assert numbers["owner_pay"]["safe_per_payment"] == core.safe_owner_pay()["safe"]


def test_spending_later_is_never_less_safe():
    """Spending today hits every day ahead; the closed form takes the whole horizon, so a date in a
    week is at least as safe (a sanity check of the shortcut against a real what-if)."""
    core = import_business("estudio-lapiz-rojo", with_one_offs=True)
    line = core.status().business.low_cash_line
    amount = core.safe_to_spend()["amount"]
    later = (core.today + timedelta(days=7)).isoformat()
    assert _worst_after(core, [{"type": "one_time_expense", "amount": amount, "date": later}]) >= line - 1


def test_chat_never_says_zero_pay_is_safe():
    """Seen in the browser: "up to $0 per payment keeps a bad month above the line" (it doesn't)."""
    from aheadly.ai.templates import answer_from_tool

    data = {
        "horizon_weeks": 8,
        "safe_to_spend_now": 0,
        "low_cash_line": 2000,
        "lowest_worst_case": -2395,
        "owner_pay": {
            "payment": "Owner transfer",
            "now_per_payment": 690,
            "safe_per_payment": 0,
            "how_often": "weekly",
        },
    }
    text = answer_from_tool("safe_to_spend", data)
    assert "up to $0" not in text and "even pausing it" in text
