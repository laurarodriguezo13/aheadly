"""Deterministic, number-safe text built straight from facts and tool results.

Used by the offline StubClient and as the graceful fallback whenever a real
LLM call fails or the guardrail rejects its answer twice.
"""

from __future__ import annotations

from datetime import date


def money(value: float) -> str:
    value = round(value)
    return f"-${-value:,}" if value < 0 else f"${value:,}"


def day(iso: str) -> str:
    """'2026-12-15' → 'Dec 15, 2026' (anything else is returned as it is)."""
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%b %d, %Y").replace(" 0", " ")
    except ValueError:
        return str(iso)


def weeks(n: int) -> str:
    return "1 week" if n == 1 else f"{n} weeks"


def answer_from_tool(tool: str, data: dict) -> str:
    if "error" in data:
        return f"I couldn't do that: {data['error']} Try asking in another way."
    if tool == "run_scenario":
        s = data["scenario"]
        verdict = {
            "safe": "That looks safe: even in a bad month you stay above your low cash line.",
            "watch": (
                "Your base case stays above your low cash line, but in a bad month you could dip below it, "
                "so keep an eye on it."
            ),
            "act_now": "That still looks tight, so I would wait or change something else first.",
        }[data["risk_level"]]
        return (
            f"If you do that, your lowest balance would be about {money(s['lowest_base_case'])} "
            f"around {day(s['lowest_date'])} (worst case {money(s['lowest_worst_case'])}, best case "
            f"{money(s['lowest_best_case'])}). Your low cash line is {money(data['low_cash_line'])}. {verdict}"
        )
    if tool == "get_forecast":
        low = data["lowest_point"]
        verdict = {
            "safe": "you stay above your low cash line, even in a bad month.",
            "watch": (
                "you stay above your low cash line in the base case, but in a bad month you could dip to "
                f"about {money(data['lowest_worst_case'])}, so keep an eye on it."
            ),
            "act_now": "you would dip below your low cash line, so it is worth acting early.",
        }[data["risk_level"]]
        period = (
            f"Between now and {day(data['until'])}"
            if data.get("until")
            else f"Over the next {data['weeks']} weeks"
        )
        return (
            f"{period} your lowest point is about {money(low['balance_base_case'])} "
            f"on {day(low['date'])}, which means {verdict}"
        )
    if tool == "get_cash_summary":
        return (
            f"You have {money(data['current_balance'])} today. In the last 30 days {money(data['money_in_30d'])} "
            f"came in and {money(data['money_out_30d'])} went out. Your low cash line is {money(data['low_cash_line'])}."
        )
    if tool == "get_upcoming_outflows":
        lines = ", ".join(
            f"{o['label']} {money(o['amount'])} on {day(o['date'])}" for o in data["outflows"][:3]
        )
        return f"The biggest payments coming up are: {lines}. Plan for those first."
    if tool == "get_alerts":
        if not data["alerts"]:
            return "You have no open alerts right now. Things look calm."
        first = data["alerts"][0]
        return f"{first['title']}: {first['body']}"
    if tool == "get_transactions":
        return f"Here are your last {len(data['transactions'])} transactions."
    if tool == "propose_plan_items":
        if not data["proposed"]:
            return 'I couldn\'t find a payment or income in that. Try with the amount and the day, like "$1,650 on Dec 2".'
        parts = []
        for item in data["proposed"]:
            way = "coming in" if item["direction"] == "in" else "going out"
            amount = money(item["amount"]) if item["amount"] else "an amount you didn't say"
            when = f" on {_short_date(item['due_date'])}" if item["due_date"] else ""
            parts.append(f"{item['label']}, {amount} {way}{when}")
        return (
            "Here's what I understood: "
            + "; ".join(parts)
            + ". It isn't saved yet: check it below and press Add."
        )
    return "Here is what I found."


def _short_date(iso: str) -> str:
    """'2026-12-02' → 'Dec 2'."""
    d = date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


def alert_title(facts: dict) -> str:
    """How serious it is, from the numbers: code picks the title, the model only writes the body."""
    if facts["type"] == "idle_cash":
        return "Good news: you have cash to spare"
    if facts["lowest_balance"] < 0:
        return "Warning: your cash could run out"
    return "Heads up: you may run low on cash"


def alert_text(facts: dict) -> dict:
    if facts["type"] == "idle_cash":
        return {
            "title": alert_title(facts),
            "body": (
                f"Even in a bad case your balance stays above {money(facts['lowest_worst_case'])} for the next "
                f"8 weeks. That money could work harder for you."
            ),
            "actions": [
                {"label": "Pay a supplier early", "detail": "Ask for a discount in exchange."},
                {"label": "Buy inventory in bulk", "detail": "Lock in prices with your main suppliers."},
            ],
        }
    outflows = facts["top_outflows"]
    # payment names as written (lowercasing them broke names like "Christmas ingredients")
    cause = " and ".join(f"{o['label']} ({money(o['amount'])})" for o in outflows[:2])
    return {
        "title": alert_title(facts),
        "body": (
            f"Your balance could drop to about {money(facts['lowest_balance'])} in {weeks(facts['weeks_ahead'])}, "
            f"below your {money(facts['low_cash_line'])} line, because {cause} land close together."
        ),
        "actions": [
            {
                "label": "Delay the planned purchase",
                "detail": "Moving a big purchase by a few weeks changes a lot.",
            },
            {
                "label": "Collect invoices early",
                "detail": "Ask customers who owe you to pay a little sooner.",
            },
            {"label": "Negotiate payment terms", "detail": "Split the big supplier bill in two."},
        ],
    }
