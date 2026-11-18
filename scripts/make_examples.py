"""Roadmap 5.6: build the example businesses in `aheadly/examples/` from the six test businesses.

Each example gets copies of its test business's bank statements and an `example.json`: the profile,
the balance to type for a statement without a Balance column, the one-off payments its owner knows
about and the owner's onboarding answers, all taken from `tests/businesses/<slug>/answer_key.json`.
The test businesses are only read, never changed. A test keeps the copies identical, so run this
again if a test business ever changes: `uv run python -m scripts.make_examples`
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUSINESSES = ROOT / "tests" / "businesses"
EXAMPLES = ROOT / "aheadly" / "examples"
STATEMENTS = ("bank_statement", "card_statement")
ABOUT = (
    "Roadmap 1.5 / 5.6 example business, made by scripts/make_examples.py from "
    "tests/businesses/{slug}: the statements are copies (a test checks they stay identical); "
    "upcoming items are the one-offs its owner knows about and answers are the owner's onboarding "
    "answers, both from that business's answer key, used to pre-fill the questions."
)


def owner_first_name(readme: str) -> str:
    """The first word of the README's story: "Maria Gómez (45) runs a bakery…" → "Maria"."""
    story = readme.split("## Story", 1)[-1].strip()
    found = re.match(r"[^\W\d_]+", story)
    return found.group(0) if found else ""


def first_capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def example_for(slug: str) -> tuple[dict, list[Path]]:
    folder = BUSINESSES / slug
    key = json.loads((folder / "answer_key.json").read_text(encoding="utf-8"))
    business, answers = key["business"], key["onboarding_answers"]
    statements = [folder / f["path"] for f in key["files"] if f["kind"] in STATEMENTS]
    typed = key["import"]["balance_to_type_if_no_column"]
    balances = {
        (folder / f["path"]).name: typed
        for f in key["files"]
        if f["kind"] in STATEMENTS and not f["has_balance"] and typed is not None
    }
    info = {
        "_about": ABOUT.format(slug=slug),
        "profile": {
            "name": business["name"],
            "owner_name": owner_first_name((folder / "README.md").read_text(encoding="utf-8")),
            "city": business.get("city", ""),
            "low_cash_line": float(business["low_cash_line"]),
        },
        **({"balances": balances} if balances else {}),
        "upcoming": [
            {
                "label": o["label"],
                "amount": o["amount"],
                "date": o["date"],
                "certainty": "confirmed" if o["certainty"] == "confirmed" else "maybe",
            }
            for o in sorted(key["one_offs_known"], key=lambda o: o["date"])
        ],
        "answers": {
            "business_type": first_capital(answers["business_type"]),
            "customers_pay": first_capital(answers["customers_pay"]),
            "busy_months": [int(m[5:7]) for m in answers["busy_months"]],
            "slow_months": [int(m[5:7]) for m in answers["slow_months"]],
            "owner_pay": (
                [answers["owner_pay"]["match_hint"]] if answers["owner_pay"]["is_owner_pay"] else []
            ),
            "mystery": dict(answers["mystery_answers"]),
        },
    }
    return info, statements


def main() -> None:
    for folder in sorted(BUSINESSES.iterdir()):
        if not (folder / "answer_key.json").is_file():
            continue
        info, statements = example_for(folder.name)
        target = EXAMPLES / folder.name
        if (target / "statements").exists():
            shutil.rmtree(target / "statements")
        (target / "statements").mkdir(parents=True)
        for path in statements:
            shutil.copyfile(path, target / "statements" / path.name)
        (target / "example.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{folder.name}: {len(statements)} statement(s), {len(info['upcoming'])} upcoming")


if __name__ == "__main__":
    main()
