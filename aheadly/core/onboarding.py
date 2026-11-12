"""Onboarding questions (roadmap 2.7): detect first, then ask.

After the upload the app already knows a lot (recurring payments, categories, transfers between the
owner's own accounts). It asks only what the statement can't show, at most about ten questions,
each saying why it matters, all skippable, and it remembers where the owner left off. Answers go
through the same App Core methods the rest of the app uses (payee rules, busy months, plan items).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from aheadly.ai.categorizer import plain

MAX_QUESTIONS = 10
MAX_MYSTERIES = 5
# money sent to a savings or personal account in someone's name: often the owner paying themselves
OWN_ACCOUNT = re.compile(r"\b(cta|cuenta)\b.*\bahorros?\b|\bsavings\b|\bpersonal\b|\bowner\b")

WHY = {
    "business": "So we know what's normal for your kind of business before we point anything out.",
    "seasons": (
        "The forecast learns from your last few months. If December or January is very different, "
        "it needs to know."
    ),
    "owner_pay": (
        "Your own pay is the one cost you can change yourself when cash is tight, so we treat it apart "
        "from the business's costs."
    ),
    "mystery": "So your spending by category adds up, and a payment we can't name doesn't hide a problem.",
    "coming_up": "Your statement only shows the past. Big payments you already know about change the forecast.",
}


@dataclass(frozen=True)
class Question:
    id: str
    kind: str  # business | seasons | owner_pay | mystery | coming_up
    title: str
    why: str
    payee: str | None = None
    amount: float | None = None  # money out is negative
    detail: str = ""  # how often / how much, in plain words
    suggestion: str | None = None  # a category the model suggests (mystery questions)
    reason: str = ""
    extra: dict = field(default_factory=dict)


def build(
    profile: dict,
    payees: list[dict],
    suggestions: dict[str, tuple[str, str]],
    how_often: dict[str, str],
) -> list[Question]:
    """All questions for this business, in the order they're asked (answered ones included; the
    caller leaves out what's done). `payees`: lines still in "other" over the last three months
    ({description, count, total}), biggest first. `suggestions`: payee → (category, reason).
    `how_often`: payee key → "weekly (Fridays)" for payees found to repeat."""
    questions = [
        Question(
            "business",
            "business",
            "What does your business do, and how do your customers pay you?",
            WHY["business"],
        ),
        Question("seasons", "seasons", "Which months are usually busy or slow?", WHY["seasons"]),
    ]
    owner_pay = [p for p in payees if p["total"] < 0 and OWN_ACCOUNT.search(plain(p["description"]))]
    for p in owner_pay[:2]:
        often = how_often.get(plain(p["description"]))
        questions.append(
            Question(
                f"owner_pay:{plain(p['description'])}",
                "owner_pay",
                f"Is {p['description']} your own pay?",
                WHY["owner_pay"],
                payee=p["description"],
                amount=p["total"],
                detail=_detail(p, often),
            )
        )
    shown = {q.payee for q in questions}
    mysteries = [p for p in payees if p["description"] not in shown]
    for p in mysteries[:MAX_MYSTERIES]:
        key = plain(p["description"])
        category, reason = suggestions.get(p["description"], (None, ""))
        questions.append(
            Question(
                f"mystery:{key}",
                "mystery",
                f"What is {p['description']}?",
                WHY["mystery"],
                payee=p["description"],
                amount=p["total"],
                detail=_detail(p, how_often.get(key)),
                suggestion=category,
                reason=reason,
            )
        )
    questions.append(
        Question("coming_up", "coming_up", "Anything big coming up in the next two months?", WHY["coming_up"])
    )
    return questions[:MAX_QUESTIONS]


def _detail(payee: dict, how_often: str | None) -> str:
    total = abs(payee["total"])
    times = payee["count"]
    where = "out" if payee["total"] < 0 else "in"
    if how_often:
        each = total / times if times else total
        return f"About ${each:,.0f} {how_often}, money {where}."
    return f"{times} time{'s' if times != 1 else ''} in the last 3 months, ${total:,.0f} in total, money {where}."
