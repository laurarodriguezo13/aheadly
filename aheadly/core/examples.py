"""Roadmap 1.5 and 5.6: ready-made businesses anyone can try without their own files.

An example lives in `aheadly/examples/<slug>/`: its bank statements (read exactly like an owner's
upload) and `example.json` (the business profile, the balance to type for a statement without a
Balance column, the upcoming payments its owner knows about and their onboarding answers). The six
examples are the six test businesses, made by `scripts/make_examples.py`, so each is one the
automatic checks have looked at (DECISIONS #28, #60).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from aheadly.domain import ScheduledItem

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
DEFAULT_EXAMPLE = "panaderia-la-esquina"
ORDER = (  # the picker's order (roadmap 5.6): the bakery first, then from tight to comfortable
    DEFAULT_EXAMPLE,
    "cafe-la-tertulia",
    "ferreteria-don-perno",
    "disfraces-la-fantasia",
    "taller-los-pistones",
    "estudio-lapiz-rojo",
)


@dataclass(frozen=True)
class Example:
    slug: str
    profile: dict
    statements: list[tuple[str, bytes]]  # (file name, file content)
    upcoming: list[ScheduledItem]
    answers: dict = field(default_factory=dict)  # the owner's onboarding answers (roadmap 2.7)
    balances: dict = field(default_factory=dict)  # statement file name → balance to type (no Balance column)


def list_examples() -> list[str]:
    """Every example business there is, in the picker's order."""
    found = {p.name for p in EXAMPLES.iterdir() if (p / "example.json").is_file()}
    return [s for s in ORDER if s in found] + sorted(found - set(ORDER))


def example_names() -> dict[str, str]:
    """slug → the business's name, in the picker's order (reads only each example.json)."""
    return {
        slug: json.loads((EXAMPLES / slug / "example.json").read_text(encoding="utf-8"))["profile"]["name"]
        for slug in list_examples()
    }


def load_example(slug: str = DEFAULT_EXAMPLE) -> Example:
    folder = EXAMPLES / slug
    if not (folder / "example.json").is_file():
        raise ValueError(f"There is no example business called {slug!r}.")
    info = json.loads((folder / "example.json").read_text(encoding="utf-8"))
    statements = [
        (path.name, path.read_bytes())
        for path in sorted((folder / "statements").iterdir())
        if path.suffix.lower() in (".csv", ".xlsx")
    ]
    upcoming = [
        ScheduledItem(
            label=item["label"],
            amount=float(item["amount"]),
            due_date=date.fromisoformat(item["date"]),
            kind="receivable" if item["amount"] > 0 else "bill",
            source="example",
            certainty=item.get("certainty", "confirmed"),
        )
        for item in info["upcoming"]
    ]
    return Example(
        slug,
        dict(info["profile"]),
        statements,
        upcoming,
        dict(info.get("answers", {})),
        dict(info.get("balances", {})),
    )
