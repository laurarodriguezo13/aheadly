"""Roadmap 2.2: put every bank line in a category (sales, payroll, rent, suppliers...).

Order, first match wins:
  1. the owner's own answers (payee rules): "TRANSF 0045 REF 88213 is my equipment loan";
  2. moves between the owner's own accounts (found by `core/transfers.py`);
  3. a category the file itself carried (the app's own CSV format, the demo data);
  4. keyword rules for the way Colombian and US banks word things (below);
  5. defaults: money in is sales, a PSE payment to a company is a supplier, anything else is other.

No language model: bank lines are short codes ("PAGO PILA APORTES", "GMF 4X1000"), which rules read
better than a general model, and the rules are explainable and testable (DECISIONS #29). Lines the
rules can't place (a transfer with only a reference number) are what the onboarding questions ask
about (roadmap 2.7); the answer becomes a payee rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aheadly.data.connectors.csv_connector import plain

# every category, in the order the app lists them
CATEGORIES = (
    "sales",
    "other_income",
    "payroll",
    "owner_pay",
    "rent",
    "utilities",
    "suppliers",
    "taxes",
    "loan",
    "equipment",
    "bank_fees",
    "other",
    "transfer_internal",
    "card_payment",
)

# (category, direction, words). Direction: "in" (money in), "out" (money out) or "any".
# Words are matched on whole words of the plain text (lower case, no accents). Order matters.
KEYWORD_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("bank_fees", "out", ("gmf", "4x1000", "4 x 1000", "cuota manejo", "cuota de manejo", "comision")),
    ("bank_fees", "out", ("bank fee", "service charge", "maintenance fee", "overdraft", "wire fee")),
    ("card_payment", "out", ("pago tarjeta", "tarjeta credito", "pago tc", "credit card payment")),
    ("taxes", "out", ("dian", "impuesto", "impuestos", "iva", "retencion", "reteica", "predial", "ica")),
    ("taxes", "out", ("irs", "tax", "taxes", "sales tax", "eftps")),
    ("payroll", "out", ("nomina", "pila", "aportes", "seguridad social", "salario", "salarios", "cesantias")),
    ("payroll", "out", ("prima de servicios", "liquidacion", "payroll", "salary", "wages", "adp", "gusto")),
    ("owner_pay", "out", ("owner draw", "owner's draw", "owners draw", "owner distribution")),
    ("rent", "out", ("arriendo", "arrendamiento", "alquiler", "canon", "administracion", "rent", "lease")),
    ("rent", "out", ("administration fee", "building fee", "hoa", "landlord")),
    (
        "utilities",
        "out",
        (
            "enel",
            "codensa",
            "vanti",
            "epm",
            "emcali",
            "essa",
            "air-e",
            "afinia",
            "celsia",
            "electricaribe",
            "eaab",
            "triple a",
            "acueducto",
            "alcantarillado",
            "aguas",
            "energia",
            "gas natural",
            "gases",
            "claro",
            "movistar",
            "tigo",
            "etb",
            "internet",
            "electricity",
            "water bill",
            "comcast",
            "verizon",
            "at&t",
        ),
    ),
    ("loan", "any", ("credito", "prestamo", "leasing", "loan", "rotativo", "desembolso", "financiacion")),
    (
        "equipment",
        "out",
        (
            "maquinaria",
            "maquina",
            "equipo",
            "equipment",
            "horno",
            "batidora",
            "molino",
            "nevera",
            "congelador",
            "computador",
            "portatil",
            "impresora",
            "laptop",
            "maniqui",
            "maniquies",
            "vitrina",
            "estanteria",
            "mobiliario",
        ),
    ),
    ("other_income", "in", ("intereses", "interest", "rendimientos", "reembolso", "refund")),
    (
        "suppliers",
        "out",
        (
            "proveedor",
            "proveedores",
            "supplier",
            "distribuidora",
            "mayorista",
            "insumos",
            "materia prima",
            "empaques",
            "packaging",
            "inventory",
            "wholesale",
            "ingredients",
            "raw materials",
            "merchandise",
            "makro",
            "mercadolibre",
        ),
    ),
    (
        "other",
        "out",
        (
            # software and subscriptions
            "adobe",
            "figma",
            "google",
            "microsoft",
            "siigo",
            "alegra",
            "loggro",
            "canva",
            "zoom",
            "dropbox",
            "netflix",
            "spotify",
            # fuel and everyday purchases
            "terpel",
            "primax",
            "texaco",
            "biomax",
            "olimpica",
            "exito",
            "carulla",
            "jumbo",
            "juan valdez",
            "panamericana",
        ),
    ),
)

# answers in the owner's own words ("loan for the car lift") also go through KEYWORD_RULES; these
# phrases only make sense in an answer
ANSWER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("owner_pay", ("my pay", "my salary", "owner pay", "pay myself", "mi sueldo", "mi salario")),
    (
        "transfer_internal",
        ("my old account", "my own account", "my other account", "own account", "mi cuenta", "mis cuentas"),
    ),
    ("loan", ("loan", "leasing", "credit line", "prestamo", "credito")),
)


@dataclass(frozen=True)
class Line:
    id: int
    description: str
    amount: float
    category: str | None  # what the file said ("other" when it said nothing)
    category_source: str | None  # bank (from the file) | rule | owner
    is_internal_transfer: bool


@dataclass(frozen=True)
class PayeeRule:
    match_key: str  # plain text of the payee, e.g. "transf 0045 ref 88213"
    category: str


def match_key(text: str) -> str:
    """The plain form of a payee or description that rules are matched on."""
    return plain(text)


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def by_keywords(description: str, amount: float) -> str:
    """Steps 4 and 5: the category the bank wording suggests, or the default."""
    text = plain(description)
    direction = "in" if amount > 0 else "out"
    for category, rule_direction, words in KEYWORD_RULES:
        if rule_direction in (direction, "any") and any(_has(text, w) for w in words):
            return category
    if direction == "in":
        return "sales"
    if _has(text, "pse"):
        return "suppliers"
    return "other"


def category_from_answer(answer: str, amount: float = -1.0) -> str:
    """The category an owner's answer in their own words points to ('my accountant's fee' → other)."""
    text = plain(answer)
    for category, phrases in ANSWER_RULES:
        if any(_has(text, p) for p in phrases):
            return category
    found = by_keywords(answer, amount)
    return found if found in CATEGORIES else "other"


def categorize(line: Line, rules: list[PayeeRule]) -> tuple[str, str]:
    """(category, source) for one line. Source: owner | rule | bank."""
    text = plain(line.description)
    for rule in rules:
        if rule.match_key and _has(text, rule.match_key):
            return rule.category, "owner"
    if line.is_internal_transfer:
        return ("card_payment" if line.category == "card_payment" else "transfer_internal"), "rule"
    if line.category_source in (None, "bank") and line.category not in (None, "", "other"):
        return line.category, "bank"
    return by_keywords(line.description, line.amount), "rule"
