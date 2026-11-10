"""Deterministic, number-safe text built straight from facts and tool results.

Used by the offline StubClient and as the graceful fallback whenever a real
LLM call fails or the guardrail rejects its answer twice.
"""

from __future__ import annotations


def money(value: float) -> str:
    value = round(value)
    return f"-${-value:,}" if value < 0 else f"${value:,}"


def weeks(n: int) -> str:
    return "1 week" if n == 1 else f"{n} weeks"


def answer_from_tool(tool: str, data: dict) -> str:
    if "error" in data:
        return f"I couldn't do that: {data['error']} Try asking in another way."
    if tool == "run_scenario":
        s = data["scenario"]
        verdict = (
            "That looks safe."
            if data["stays_above_low_cash_line"]
            else "That still looks tight, so I would wait or change something else first."
        )
        return (
            f"If you do that, your lowest balance would be about {money(s['lowest_base_case'])} "
            f"around {s['lowest_date']} (worst case {money(s['lowest_worst_case'])}, best case "
            f"{money(s['lowest_best_case'])}). Your low cash line is {money(data['low_cash_line'])}. {verdict}"
        )
    if tool == "get_forecast":
        low = data["lowest_point"]
        verdict = (
            "you stay above your low cash line."
            if low["balance_base_case"] >= data["low_cash_line"]
            else "you would dip below your low cash line, so it is worth acting early."
        )
        return (
            f"Over the next {data['weeks']} weeks your lowest point is about {money(low['balance_base_case'])} "
            f"on {low['date']}, which means {verdict}"
        )
    if tool == "get_cash_summary":
        return (
            f"You have {money(data['current_balance'])} today. In the last 30 days {money(data['money_in_30d'])} "
            f"came in and {money(data['money_out_30d'])} went out. Your low cash line is {money(data['low_cash_line'])}."
        )
    if tool == "get_upcoming_outflows":
        lines = ", ".join(f"{o['label']} {money(o['amount'])} on {o['date']}" for o in data["outflows"][:3])
        return f"The biggest payments coming up are: {lines}. Plan for those first."
    if tool == "get_alerts":
        if not data["alerts"]:
            return "You have no open alerts right now. Things look calm."
        first = data["alerts"][0]
        return f"{first['title']}: {first['body']}"
    if tool == "get_transactions":
        return f"Here are your last {len(data['transactions'])} transactions."
    return "Here is what I found."


def alert_text(facts: dict) -> dict:
    if facts["type"] == "idle_cash":
        return {
            "title": "Good news: you have cash to spare",
            "body": (
                f"Even in a bad case your balance stays above {money(facts['lowest_worst_case'])} for the next "
                f"8 weeks. That money could work harder for you."
            ),
            "actions": [
                {"label": "Pay a supplier early", "detail": "Ask for a discount in exchange."},
                {"label": "Buy inventory in bulk", "detail": "Lock in prices on flour and dairy."},
            ],
        }
    outflows = facts["top_outflows"]
    cause = " and ".join(f"{o['label'].lower()} ({money(o['amount'])})" for o in outflows[:2])
    return {
        "title": "Heads up: you may run low on cash",
        "body": (
            f"Your balance could drop to about {money(facts['lowest_balance'])} in {weeks(facts['weeks_ahead'])}, "
            f"below your {money(facts['low_cash_line'])} line, because {cause} land close together."
        ),
        "actions": [
            {
                "label": "Delay the planned purchase",
                "detail": "Moving a big purchase by a few weeks changes a lot.",
            },
            {"label": "Collect invoices early", "detail": "Ask the cafés to pay a little sooner."},
            {"label": "Negotiate payment terms", "detail": "Split the big supplier bill in two."},
        ],
    }
