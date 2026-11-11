"""Roadmap 1.5: a ready-made business anyone can try without their own files.

An example lives in `aheadly/examples/<slug>/`: its bank statements (read exactly like an owner's
upload) and `example.json` (the business profile and the upcoming payments its owner knows about).
The bakery's statements are copies of a test business, so the example is always one the
automatic checks have looked at (DECISIONS #28).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from aheadly.domain import ScheduledItem

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
DEFAULT_EXAMPLE = "panaderia-la-esquina"


@dataclass(frozen=True)
class Example:
    slug: str
    profile: dict
    statements: list[tuple[str, bytes]]  # (file name, file content)
    upcoming: list[ScheduledItem]


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
    return Example(slug, dict(info["profile"]), statements, upcoming)
