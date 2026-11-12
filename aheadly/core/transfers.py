"""Money moved between the owner's own accounts is neither income nor spending.

A transfer shows up twice: money out of one uploaded account and the same amount into another,
within a few days (the two banks may book it on different days and describe it differently).
Paying the credit card from the bank is the same thing: the card's purchases are the spending,
the payment only settles the card. Money sent to an account we don't have (the owner's personal
account, a supplier) has no matching side, so it stays real money out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

MAX_DAYS_APART = 3


@dataclass(frozen=True)
class Line:
    id: int
    account_id: int
    account_kind: str  # bank | card
    date: date
    amount: float


@dataclass(frozen=True)
class Transfer:
    out_id: int
    in_id: int
    card_payment: bool  # one side is a credit card


def find_transfers(lines: list[Line]) -> list[Transfer]:
    """Pair each money-out line with the closest same-amount money-in line of ANOTHER account,
    at most MAX_DAYS_APART days away. Each line is used once."""
    incoming: dict[float, list[Line]] = {}
    for line in lines:
        if line.amount > 0:
            incoming.setdefault(round(line.amount, 2), []).append(line)
    used: set[int] = set()
    pairs = []
    for out in sorted((x for x in lines if x.amount < 0), key=lambda x: (x.date, x.id)):
        candidates = [
            x
            for x in incoming.get(round(-out.amount, 2), [])
            if x.id not in used
            and x.account_id != out.account_id
            and abs((x.date - out.date).days) <= MAX_DAYS_APART
        ]
        if not candidates:
            continue
        match = min(candidates, key=lambda x: (abs((x.date - out.date).days), x.date, x.id))
        used.add(match.id)
        pairs.append(Transfer(out.id, match.id, "card" in (out.account_kind, match.account_kind)))
    return pairs
