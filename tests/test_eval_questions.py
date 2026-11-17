"""Roadmap 5.4: every question in tests/eval_questions.json, asked of the offline chat (the one CI can
run, and the one that answers when Gemini fails). Questions it can't handle yet are strict expected
failures with their reason, so the list in the file is also the to-do list. scripts/eval_live.py asks
the same questions of the connected model."""

from __future__ import annotations

import pytest

from tests.chat_eval import business_core, load_questions, problems

QUESTIONS = load_questions()
_CORES: dict = {}


def _core(slug: str):
    if slug not in _CORES:  # one upload per business; each question starts a fresh conversation
        _CORES[slug] = business_core(slug)
    core = _CORES[slug]
    core.clear_chat()
    return core


def _params() -> list:
    out = []
    for item in QUESTIONS:
        marks = []
        if item["offline"] is not True:
            marks = [pytest.mark.xfail(strict=True, reason=f"offline chat: {item['offline']}")]
        out.append(pytest.param(item, id=item["id"], marks=marks))
    return out


@pytest.mark.parametrize("item", _params())
def test_chat_answers_well(item):
    answer = _core(item["business"]).ask(item["question"])
    assert problems(item, answer) == []


def test_the_set_is_well_formed():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids)) and 20 <= len(ids) <= 40
    assert {q["lang"] for q in QUESTIONS} == {"en", "es"}
    keys = {
        "id",
        "business",
        "lang",
        "question",
        "tools",
        "must_include",
        "must_not_include",
        "offline",
        "why",
    }
    assert all(set(q) == keys for q in QUESTIONS)
    assert all(q["offline"] is True or (isinstance(q["offline"], str) and q["offline"]) for q in QUESTIONS)


def test_the_checks_catch_a_bad_answer():
    """A made-up number, the wrong tool, a long answer, a missing word: each is caught."""
    from aheadly.domain import ChatAnswer

    item = {
        "question": "How can I fix my alert?",
        "tools": ["get_alerts"],
        "must_include": ["oven"],
        "must_not_include": ["Dec 31"],
    }
    good = ChatAnswer(
        "Move the oven to Dec 16: lowest $3,693.", ["get_alerts"], facts=[{"lowest": 3693, "d": "2026-12-16"}]
    )
    assert problems(item, good) == []
    invented = ChatAnswer("Move the oven: you'd have $9,999.", ["get_alerts"], facts=[{"lowest": 3693}])
    assert any("numbers" in p for p in problems(item, invented))
    wrong_tool = ChatAnswer("Move the oven.", ["get_cash_summary"])
    assert any("expected one of" in p for p in problems(item, wrong_tool))
    long = ChatAnswer("oven " * 121, ["get_alerts"])
    assert any("words" in p for p in problems(item, long))
    off = ChatAnswer("Pay it on Dec 31.", ["get_alerts"], facts=[{"d": "2026-12-31"}])
    assert {"missing 'oven'", "should not say 'Dec 31'"} <= set(problems(item, off))
    asks = {**item, "tools": []}
    assert any("ask back" in p for p in problems(asks, good))
