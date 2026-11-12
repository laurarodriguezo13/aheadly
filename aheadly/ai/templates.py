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
            + chance_clause(s.get("chance_below_line_pct"))
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
            f"on {day(low['date'])}, which means {verdict}" + chance_clause(data.get("chance_below_line_pct"))
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


def chance_clause(pct: int | None) -> str:
    """For chat answers (roadmap 3.1): ' The chance of dipping below your line: about 64%.'"""
    if pct is None:
        return ""
    if pct == 0:
        return " None of the ways the coming weeks could go dips below your line."
    if pct == 100:
        return " Every way the coming weeks could go dips below your line."
    return f" The chance of dipping below your line: about {pct}%."


def chance_sentence(pct: int | None) -> str:
    """For the alert (roadmap 3.1): ' About 64% of the ways the coming weeks could go dip below it.'"""
    if pct is None:
        return ""
    if pct == 0:
        return " None of the ways the coming weeks could go dips below it."
    if pct == 100:
        return " Every way the coming weeks could go dips below it."
    return f" About {pct}% of the ways the coming weeks could go dip below it."


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
                {
                    "label": "Pay a supplier early",
                    "detail": "Ask for a discount in exchange.",
                    "how_to": [
                        "Pick a supplier you pay every month.",
                        "Offer to pay early for a small discount.",
                    ],
                },
                {
                    "label": "Buy inventory in bulk",
                    "detail": "Lock in prices with your main suppliers.",
                    "how_to": [
                        "Ask your main supplier for a bulk price.",
                        "Buy only what you use in the next months.",
                    ],
                },
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
            + chance_sentence(facts.get("chance_below_line_pct"))
        ),
        "actions": [
            {
                "label": "Delay the planned purchase",
                "detail": "Moving a big purchase by a few weeks changes a lot.",
                "how_to": [
                    "Look at what you plan to buy in the tight week.",
                    "Ask whether it can wait a few weeks.",
                ],
            },
            {
                "label": "Collect invoices early",
                "detail": "Ask customers who owe you to pay a little sooner.",
                "how_to": ["List who owes you money.", "Ask the biggest ones to pay a little sooner."],
            },
            {
                "label": "Negotiate payment terms",
                "detail": "Split the big supplier bill in two.",
                "how_to": [
                    "Call the supplier before the bill is due.",
                    "Ask to pay half now and half later.",
                ],
            },
        ],
    }


# ------------------------------------------------------------- actions (roadmap 3.2)
def action_words(
    kind: str,
    payee: str = "",
    amount: float = 0.0,
    when: str | None = None,
    new_when: str | None = None,
    pct: int = 0,
    weekly: float = 0.0,
) -> dict:
    """Label, detail and how-to steps for a suggestion worked out by code (it names the real payment)."""
    if kind == "owner_pay":
        label = (
            "Pause your own pay for the next 8 weeks"
            if pct >= 100
            else f"Pay yourself {pct}% less for the next 8 weeks"
        )
        return {
            "label": label,
            "detail": f"{payee}: {money(amount)} each time, {money(amount * (100 - pct) / 100)} instead.",
            "how_to": [
                "Work out what you need to live on for the next weeks.",
                "Change or skip the transfer to your own account until the tight weeks pass.",
                "Press Test this, then Save as my plan.",
            ],
        }
    if kind == "price":
        return {
            "label": f"Raise prices about {pct}%",
            "detail": f"If customers keep buying as they do now, about {money(weekly * pct / 100)} more comes in each week.",
            "how_to": [
                "Start with your best-selling items.",
                "Tell regular customers ahead, and keep quality the same.",
                "Press Test this; check your sales for two weeks before counting on it.",
            ],
        }
    old, new = _short_date(when), _short_date(new_when)
    if kind == "move_payment":
        return {
            "label": f"Move {payee} to {new}",
            "detail": f"Ask to pay the {money(amount)} due {old} on {new} instead.",
            "how_to": [
                f"Call or message them this week, before {old}.",
                f"Ask to pay on {new} instead of {old}, and confirm the new date in writing.",
                "If they agree, press Test this, then Save as my plan so the forecast uses the new date.",
            ],
        }
    return {
        "label": f"Ask for {payee} by {new}",
        "detail": f"The {money(amount)} due {old} would arrive before the tight week.",
        "how_to": [
            "Message them a few days ahead.",
            f"Ask whether they could pay by {new} instead of {old}; a small discount for paying early can help.",
            "If they agree, press Test this, then Save as my plan.",
        ],
    }


def message_text(facts: dict) -> str:
    """A short message the owner can copy and send (the app never sends it)."""
    who = (
        f"This is {facts['owner']} from {facts['business']}"
        if facts.get("owner")
        else f"This is {facts['business']}"
    )
    old, new = _short_date(facts["date"]), _short_date(facts["new_date"])
    if facts["kind"] == "move_payment":
        return (
            f"Hi! {who}. Could we move the {facts['payee']} payment of {money(facts['amount'])} from {old} "
            f"to {new}? It would really help us this month. Thank you!"
        )
    return (
        f"Hi! {who}. About {facts['payee']} ({money(facts['amount'])}, due {old}): would it be possible to "
        f"pay a little earlier, by {new}? It would really help us this month. Thank you!"
    )
