"""'Is there anything else we should know?' (roadmap R.3c): the owner's free text, sorted into limits
for the suggestions (the same rules as "Not for me") and background notes for the chat. Payments
in it are read by "just say it" (plan_text). Nothing is used before the owner confirms.

The connected model sorts it when there is one (`InsightTranslator.sort_owner_notes`); these rules
do it offline and check what the model returns: a limit's kind must be one the suggestions know,
and a payment it names must be one of the business's own.
"""

from __future__ import annotations

import re

from aheadly.ai.plan_text import amounts_in

KINDS = ("owner_pay", "price", "move_payment", "collect_early")
# a limit about one payment needs that payment; the others are about the whole kind
NEEDS_PAYMENT = ("move_payment", "collect_early")
NEGATIONS = (
    "can't",
    "cannot",
    "can not",
    "won't",
    "will not",
    "never",
    "no way",
    "not able",
    "don't",
    "do not",
)
TOPICS = {
    "owner_pay": ("my pay", "my salary", "pay myself", "my own pay", "what i take", "my wage"),
    "price": ("price", "prices", "charge more", "charging more"),
    "move_payment": (
        "move",
        "delay",
        "postpone",
        "pay later",
        "pay it later",
        "change the date",
        "push back",
    ),
    "collect_early": (
        "pay early",
        "pay sooner",
        "pay me early",
        "pay me sooner",
        "pay earlier",
        "ahead of time",
    ),
}


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip()]


def _payment_in(sentence: str, labels: list[str]) -> str | None:
    """The business's own payment the sentence names (by a distinctive word of its name)."""
    from aheadly.ai.llm_client import best_label  # the same matching the chat uses

    return best_label(sentence.lower(), labels)


def read_by_rules(text: str, labels: list[str]) -> dict:
    """Limits ("I can't lower my pay", "Molinos never moves a delivery date") and notes (the rest,
    except sentences with an amount: those are payments, read by "just say it")."""
    limits, notes = [], []
    for sentence in sentences(text):
        low = sentence.lower()
        said_no = any(n in low for n in NEGATIONS)
        found = None
        if said_no:
            for kind in ("collect_early", "owner_pay", "price", "move_payment"):
                if any(t in low for t in TOPICS[kind]):
                    payment = _payment_in(sentence, labels) if kind in NEEDS_PAYMENT else None
                    if kind in NEEDS_PAYMENT and not payment:
                        continue
                    found = {"kind": kind, "payment": payment, "quote": sentence}
                    break
        if found:
            limits.append(found)
        elif not amounts_in(sentence):
            notes.append(sentence)
    return {"limits": limits, "notes": notes}


def check(raw: dict, labels: list[str], text: str) -> dict:
    """What the model returned, kept only where it fits: known kinds, the business's own payments,
    a quote from the owner's own words; a note no longer than the owner wrote."""
    limits = []
    for limit in raw.get("limits") or []:
        kind, payment = limit.get("kind"), limit.get("payment") or None
        if kind not in KINDS:
            continue
        if payment not in labels:
            payment = None
        if kind in NEEDS_PAYMENT and not payment:
            continue
        quote = str(limit.get("quote") or "").strip() or text.strip()
        limits.append({"kind": kind, "payment": payment if kind in NEEDS_PAYMENT else None, "quote": quote})
    notes = [str(n).strip() for n in raw.get("notes") or [] if str(n).strip()]
    notes = [n for n in notes if len(n) <= max(len(text), 200)]
    return {"limits": limits, "notes": notes}


def as_rule(limit: dict) -> dict:
    """A limit the owner confirmed, as a "Not for me" rule (`actions.ruled_out`)."""
    rule = {"kind": limit["kind"], "reason": "told_us", "note": "", "what": limit["quote"]}
    if limit.get("payment"):
        rule["label"] = limit["payment"]
    return rule
