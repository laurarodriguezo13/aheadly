"""Roadmap 2.4: "Just say it". The owner writes what's coming in their own words
("I'm buying a new oven for $7,500 on Nov 14"), and the app proposes plan items to confirm.

Two readers share one output (`ProposedItem`):
  * the connected language model, through the `propose_plan_items` tool schema below;
  * `read_by_rules`, offline (the stub provider) and whenever the model fails.
Either way, code checks every item before it is shown (`check_item`): a positive amount that the
owner actually wrote, a date from today on, in or out, how often. Nothing is saved here: the owner
presses Add (DECISIONS #31).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, timedelta

REPEATS = ("once", "weekly", "every two weeks", "monthly")
RECURRENCE = {"once": None, "weekly": "weekly", "every two weeks": "biweekly", "monthly": "monthly"}
MAX_AMOUNT = 10_000_000

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "description": "Short name, e.g. 'New oven' or 'Christmas order Café Azul'",
        },
        "amount": {
            "type": "number",
            "description": "Positive amount exactly as the owner wrote it; omit if not said",
        },
        "direction": {"type": "string", "enum": ["in", "out"], "description": "in = money coming in"},
        "date": {"type": "string", "description": "YYYY-MM-DD; omit if the owner gave no day"},
        "repeats": {"type": "string", "enum": list(REPEATS)},
        "certainty": {
            "type": "string",
            "enum": ["sure", "maybe"],
            "description": "maybe for 'about', 'probably'",
        },
    },
    "required": ["label", "direction"],
}

PROPOSE_TOOL = {
    "name": "propose_plan_items",
    "description": (
        "When the owner tells you about a payment or income still to come (a purchase, a bill, a customer "
        "who will pay), propose it as plan items. Nothing is saved: the owner checks each one and presses Add."
    ),
    "parameters": {
        "type": "object",
        "properties": {"items": {"type": "array", "items": ITEM_SCHEMA}},
        "required": ["items"],
    },
}


@dataclass
class ProposedItem:
    label: str
    amount: float | None  # positive; the sign comes from direction
    direction: str  # in | out
    due_date: date | None
    repeats: str = "once"
    certainty: str = "confirmed"  # confirmed | maybe
    problem: str | None = None  # what the owner must fix before adding

    @property
    def ready(self) -> bool:
        return self.problem is None

    @property
    def signed_amount(self) -> float:
        return (self.amount or 0.0) * (1 if self.direction == "in" else -1)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["due_date"] = self.due_date.isoformat() if self.due_date else None
        return data


# ------------------------------------------------------------- checks (both readers)
def check_item(raw: dict, today: date, text: str | None = None) -> ProposedItem:
    """One proposed item from loose input (the model's tool call, an edited row). Anything wrong
    becomes `problem`, never an exception: the owner sees it and fixes it."""
    label = " ".join(str(raw.get("label") or "").split())[:80]
    direction = str(raw.get("direction") or "out").lower()
    direction = direction if direction in ("in", "out") else "out"
    repeats = str(raw.get("repeats") or "once").lower()
    repeats = repeats if repeats in REPEATS else "once"
    certainty = (
        "maybe" if str(raw.get("certainty") or "").lower() in ("maybe", "likely", "estimate") else "confirmed"
    )
    amount = _number(raw.get("amount"))
    due = _iso_date(raw.get("due_date") or raw.get("date"))
    problem = None
    if not label:
        problem = "Give it a name."
    elif amount is None or amount <= 0:
        problem = "How much?"
    elif amount > MAX_AMOUNT:
        problem = "That amount looks too big. Check it."
    elif text is not None and not any(abs(amount - a) < 0.005 for a in amounts_in(text)):
        problem = "We couldn't find this amount in what you wrote. Check it."
    elif due is None:
        problem = "When?"
    elif due < today:
        problem = "That date has already passed."
    return ProposedItem(label, amount, direction, due, repeats, certainty, problem)


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return abs(float(value))
    found = amounts_in(str(value) if "$" in str(value) else f"${value}")
    return found[0] if found else None


def _iso_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


# ------------------------------------------------------------- the offline reader
MONTHS = {
    "jan": 1, "january": 1, "ene": 1, "enero": 1,
    "feb": 2, "february": 2, "febrero": 2,
    "mar": 3, "march": 3, "marzo": 3,
    "apr": 4, "april": 4, "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "june": 6, "junio": 6,
    "jul": 7, "july": 7, "julio": 7,
    "aug": 8, "august": 8, "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "september": 9, "septiembre": 9, "set": 9,
    "oct": 10, "october": 10, "octubre": 10,
    "nov": 11, "november": 11, "noviembre": 11,
    "dec": 12, "december": 12, "dic": 12, "diciembre": 12,
}  # fmt: skip
_MONTH = r"(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
AMOUNT_RE = re.compile(
    r"(?:\$|usd\s?|us\$)\s?(\d[\d.,]*)(\s?k\b)?|(\d[\d.,]*)\s?(?:dollars|usd|d[oó]lares)\b", re.IGNORECASE
)
DATE_PATTERNS = [
    # Dec 16 and 17 · December 9 · Nov 14
    re.compile(
        rf"\b{_MONTH}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*(?:and|&|y|,)\s*(\d{{1,2}})(?:st|nd|rd|th)?\b)?",
        re.I,
    ),
    # 14 de noviembre · 14 nov
    re.compile(rf"\b(\d{{1,2}})\s+(?:de\s+)?{_MONTH}\b", re.I),
]
ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
FUZZY_RE = re.compile(
    rf"\b(early|beginning of|start of|mid|middle of|late|end of|in|a principios de|a mediados de|a finales de|en)\s+{_MONTH}\b",
    re.I,
)
FUZZY_DAY = {
    "early": 5, "beginning of": 5, "start of": 5, "a principios de": 5,
    "mid": 15, "middle of": 15, "a mediados de": 15, "in": 15, "en": 15,
    "late": 28, "end of": 28, "a finales de": 28,
}  # fmt: skip

MAYBE_WORDS = ("about", "around", "roughly", "approximately", "usually", "probably", "maybe", "might",
               "should", "expect", "early", "mid", "late", "aprox", "alrededor", "unos", "quizás", "tal vez")  # fmt: skip
IN_PHRASES = ("owes me", "owe me", "owes us", "owe us", "pays me", "pay me", "pays us", "will pay me",
              "will pay us", "ordered", "rents", "rent from us", "buys from", "customer", "client", "receive",
              "get paid", "getting paid", "income", "me debe", "nos debe", "me paga", "nos paga", "cobro",
              "cobrar", "recibo", "pedido de")  # fmt: skip
OUT_STARTS = ("i'm buying", "i am buying", "we're buying", "we are buying", "i'll buy", "i will buy", "i'm paying",
              "i am paying", "i'll pay", "i will pay", "i have to pay", "i need to pay", "we have to pay",
              "we need to pay", "we'll pay", "i owe", "we owe", "voy a comprar", "tengo que pagar", "debo pagar")  # fmt: skip
LEAD_WORDS = ("a", "an", "the", "our", "my", "both", "un", "una", "el", "la", "los", "las", "mi", "nuestro")
TRAIL_WORDS = ("for", "on", "due", "is", "are", "of", "about", "around", "roughly", "paid", "each", "and", "by",
               "at", "in", "to", "will", "be", "el", "de", "para", "por", "early", "mid", "late", "before",
               "after", "usually", "approximately", "renew", "renews")  # fmt: skip


def amounts_in(text: str) -> list[float]:
    """Every amount written with a currency sign or word: $7,500 · $3,883.34 · $5.200 · $7.5k."""
    found = []
    for match in AMOUNT_RE.finditer(text):
        raw = match.group(1) or match.group(3)
        value = _money(raw.rstrip(".,"))
        if value is not None:
            found.append(value * (1000 if match.group(2) else 1))
    return found


def _money(raw: str) -> float | None:
    """'7,500' 7500 · '3,883.34' · '1.250,00' · '5.200' (thousands) · '2,5' (decimal comma)."""
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "," in raw or "." in raw:
        sep = "," if "," in raw else "."
        parts = raw.split(sep)
        if all(len(p) == 3 for p in parts[1:]):
            raw = raw.replace(sep, "")
        elif len(parts) == 2:
            raw = raw.replace(sep, ".")
        else:
            return None
    try:
        return float(raw)
    except ValueError:
        return None


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _on_or_after(month: int, day: int, today: date, year: int | None = None) -> date | None:
    """The next such day on or after today (a month earlier than today's means next year)."""
    try:
        if year:
            return date(year if year > 100 else 2000 + year, month, day)
        candidate = date(today.year, month, day)
        return candidate if candidate >= today - timedelta(days=0) else date(today.year + 1, month, day)
    except ValueError:
        return None


def dates_in(text: str, today: date) -> tuple[list[date], list[tuple[int, int]]]:
    """Dates mentioned, in order, and the character spans they took (to take them out of the label)."""
    found: list[tuple[int, date]] = []
    spans: list[tuple[int, int]] = []
    for match in ISO_RE.finditer(text):
        d = _iso_date(match.group(0))
        if d:
            found.append((match.start(), d))
            spans.append(match.span())
    for match in SLASH_RE.finditer(text):
        if any(s <= match.start() < e for s, e in spans):
            continue
        day, month = int(match.group(1)), int(match.group(2))  # day first (Latin America)
        d = _on_or_after(month, day, today, int(match.group(3)) if match.group(3) else None)
        if d:
            found.append((match.start(), d))
            spans.append(match.span())
    for pattern_index, pattern in enumerate(DATE_PATTERNS):
        for match in pattern.finditer(text):
            if any(s <= match.start() < e for s, e in spans):
                continue
            if pattern_index == 0:
                month, days = MONTHS[match.group(1).lower()], [match.group(2), match.group(3)]
            else:
                month, days = MONTHS[match.group(2).lower()], [match.group(1)]
            for i, day in enumerate(d for d in days if d):
                d = _on_or_after(month, int(day), today)
                if d:
                    found.append((match.start() + i, d))
            spans.append(match.span())
    for match in FUZZY_RE.finditer(text):
        if any(s <= match.start() < e for s, e in spans):
            continue
        d = _on_or_after(MONTHS[match.group(2).lower()], FUZZY_DAY[match.group(1).lower()], today)
        if d:
            found.append((match.start(), d))
            spans.append(match.span())
    return [d for _, d in sorted(found, key=lambda pair: pair[0])], spans


def _fragments(text: str) -> list[str]:
    """One idea per piece: lines, sentences, semicolons, and anything in parentheses on its own."""
    pieces = []
    for line in re.split(r"[\n;]+", text):
        inside = re.findall(r"\(([^)]*)\)", line)
        line = re.sub(r"\([^)]*\)", " ", line)
        pieces += re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ])", line) + inside
    return [p.strip(" .") for p in pieces if p.strip(" .")]


def _direction(fragment: str) -> str:
    text = _plain(fragment)
    if text.startswith(OUT_STARTS):
        return "out"
    return "in" if any(re.search(rf"\b{re.escape(p)}\b", text) for p in IN_PHRASES) else "out"


def _label(fragment: str, spans: list[tuple[int, int]]) -> str:
    text = fragment
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + " " + text[end:]
    text = AMOUNT_RE.sub(" ", text)
    text = re.sub(r"\b(before|antes del?)\b", " ", text, flags=re.I)
    # "Café El Tinto Feliz owes me $800 for the hampers" → "Café El Tinto Feliz – the hampers"
    text = re.sub(
        r"\s+(?:owes|owe|pays|will pay|me debe|nos debe|me paga|nos paga)(?:\s+(?:me|us))?\s*(for|por)?\b",
        lambda m: " – " if m.group(1) else " ",
        text,
        flags=re.I,
    )
    plain = _plain(text).strip()
    for start in OUT_STARTS:
        if plain.startswith(start):
            text = text.strip()[len(start) :]
            break
    words = re.sub(r"[:,]", " ", text).split()
    while words and _plain(words[0]) in LEAD_WORDS:
        words.pop(0)
    while words and _plain(words[-1]).strip(".") in TRAIL_WORDS:
        words.pop()
    label = " ".join(words).strip(" .-")[:60]
    return label[:1].upper() + label[1:] if label else ""


def read_by_rules(text: str, today: date) -> list[ProposedItem]:
    """The offline reader. Handles the ways owners write it: '$5,500 each, paid Dec 16 and 17'
    (two items), 'about $950, early December' (a maybe), 'before Dec 20' (the day before)."""
    items: list[ProposedItem] = []
    previous = ""
    for fragment in _fragments(text):
        amounts = amounts_in(fragment)
        dates, spans = dates_in(fragment, today)
        if re.search(r"\b(before|antes del?)\s", fragment, re.I) and dates:
            dates = [d - timedelta(days=1) for d in dates]
        if not amounts and not dates:
            continue
        plain = _plain(fragment)
        direction = _direction(fragment)
        maybe = any(re.search(rf"\b{re.escape(w)}\b", plain) for w in MAYBE_WORDS)
        repeats = (
            "weekly" if re.search(r"\b(every week|weekly|cada semana|semanal)\b", plain)
            else "every two weeks" if re.search(r"\b(every two weeks|biweekly|cada dos semanas|quincenal)\b", plain)
            else "monthly" if re.search(r"\b(every month|monthly|cada mes|mensual)\b", plain)
            else "once"
        )  # fmt: skip
        label = _label(fragment, spans)
        if len(label) < 6 and previous:  # "(the other $5,200 in January)" → the deposit's second part
            label = f"{previous} (rest)"
        previous = label or previous
        if re.search(r"\b(each|cada uno|c/u)\b", plain) and len(amounts) == 1 and len(dates) > 1:
            pairs = [(amounts[0], d) for d in dates]
        elif len(amounts) == len(dates):
            pairs = list(zip(amounts, dates))
        else:
            pairs = [(amounts[0] if amounts else None, dates[0] if dates else None)]
        for i, (amount, due) in enumerate(pairs):
            name = f"{label} ({i + 1} of {len(pairs)})" if len(pairs) > 1 else label
            raw = {
                "label": name or "Upcoming payment",
                "amount": amount,
                "direction": direction,
                "date": due.isoformat() if due else None,
                "repeats": repeats,
                "certainty": "maybe" if maybe else "sure",
            }
            items.append(check_item(raw, today))
    return items


def read_tool_call(arguments: dict, today: date, text: str) -> list[ProposedItem]:
    """The model's `propose_plan_items` arguments, each item checked against the owner's own text."""
    raw_items = arguments.get("items") if isinstance(arguments, dict) else None
    if not isinstance(raw_items, list):
        return []
    return [check_item(raw, today, text) for raw in raw_items if isinstance(raw, dict)]
