"""Roadmap 5.4: the chat test set (tests/eval_questions.json), shared by the CI test
(tests/test_eval_questions.py, offline chat) and scripts/eval_live.py (the connected model)."""

from __future__ import annotations

import json
from pathlib import Path

from aheadly.ai.guardrails import check_numbers
from aheadly.core.app_core import AppCore
from aheadly.domain import ChatAnswer

QUESTIONS_FILE = Path(__file__).parent / "eval_questions.json"
MAX_WORDS = 120  # chat rule 5


def load_questions() -> list[dict]:
    return json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]


def business_core(slug: str) -> AppCore:
    """The business as its owner would have it after onboarding (the same set-up as the harness)."""
    from tests.test_businesses import import_business

    return import_business(slug, with_one_offs=True)


def problems(item: dict, answer: ChatAnswer) -> list[str]:
    """What's wrong with one answer, in words; an empty list is a pass."""
    found = []
    text = answer.text or ""
    wanted = item["tools"]
    if not wanted and answer.tool_names:
        found.append(f"should ask back, called {answer.tool_names}")
    if wanted and not set(wanted) & set(answer.tool_names):
        found.append(f"expected one of {wanted}, called {answer.tool_names or 'nothing'}")
    words = len(text.split())
    if words > MAX_WORDS:
        found.append(f"{words} words (at most {MAX_WORDS})")
    numbers = check_numbers(text, [*answer.facts, item["question"]])
    if not numbers.passed:
        found.append(f"numbers not in the tool results: {numbers.unverified}")
    lower = text.lower()
    found += [f"missing {w!r}" for w in item["must_include"] if w.lower() not in lower]
    found += [f"should not say {w!r}" for w in item["must_not_include"] if w.lower() in lower]
    return found
