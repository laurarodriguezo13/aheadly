"""Roadmap R.3c: "Is there anything else we should know?" and "What you told us"."""

import pytest

from aheadly.ai import owner_notes
from tests.test_businesses import import_business

LABELS = ["New oven", "Quarterly flour order (Molinos del Sur)", "TRANSF A CTA AHORROS M GOMEZ"]


@pytest.fixture()
def bakery():
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    core.answer_owner_pay("TRANSF A CTA AHORROS M GOMEZ", True)
    return core


def test_the_rules_sort_limits_notes_and_leave_payments_to_just_say_it():
    text = (
        "I can't lower my pay, I have a family. The oven supplier won't move the delivery date. "
        "Most of our customers are offices nearby. I'm buying flour for $900 on Dec 3."
    )
    found = owner_notes.read_by_rules(text, LABELS)
    assert [(l["kind"], l["payment"]) for l in found["limits"]] == [
        ("owner_pay", None),
        ("move_payment", "New oven"),
    ]
    assert found["notes"] == ["Most of our customers are offices nearby."]


def test_what_the_model_sends_back_is_checked():
    raw = {
        "limits": [
            {"kind": "price", "quote": "We can't charge more"},
            {"kind": "move_payment", "payment": "Rent", "quote": "Rent never moves"},  # not one of theirs
            {"kind": "fire_staff", "quote": "?"},
        ],
        "notes": ["Busy at Christmas", ""],
    }
    checked = owner_notes.check(raw, LABELS, "We can't charge more. Rent never moves. Busy at Christmas")
    assert checked == {
        "limits": [{"kind": "price", "payment": None, "quote": "We can't charge more"}],
        "notes": ["Busy at Christmas"],
    }


def test_anything_else_is_the_last_question_and_nothing_is_used_before_confirming(bakery):
    assert bakery.onboarding()["questions"][-1].kind == "anything_else"
    read = bakery.read_anything_else(
        "I can't lower my pay. We sell mostly to offices. New oven for $7,500 on Nov 20."
    )
    assert read["limits"][0]["kind"] == "owner_pay" and read["notes"] == ["We sell mostly to offices."]
    assert read["proposals"] and read["proposals"][0].amount == 7500
    assert bakery.declined_suggestions() == [] and bakery.owner_notes() == []

    bakery.keep_anything_else(read["limits"], read["notes"])
    assert all(a["kind"] != "owner_pay" for a in bakery.suggested_fixes())
    assert [n["text"] for n in bakery.owner_notes()] == ["We sell mostly to offices."]
    assert "anything_else" not in [q.id for q in bakery.onboarding()["questions"]]
    assert "We sell mostly to offices." in bakery._prompt_context(bakery._business())["owner_notes"]


def test_what_you_told_us_lists_every_answer_and_each_can_change(bakery):
    bakery.answer_business("Bakery", "card every day")
    bakery.answer_mystery("TRANSF 0045 REF 88213", words="loan repayment (equipment loan)")
    bakery.add_owner_note("Busy before Christmas")
    oven = next(a for a in bakery.suggested_fixes() if a.get("payment") == "New oven")
    bakery.decline_suggestion(oven, "wont_agree")

    told = bakery.told_us()
    assert told["business_type"] == "Bakery"
    assert [r["payee"] for r in told["owner_pay"]] == ["TRANSF A CTA AHORROS M GOMEZ"]
    [loan] = told["payees"]
    assert (loan["payee"], loan["category"], loan["said"]) == (
        "TRANSF 0045 REF 88213",
        "loan",
        "loan repayment (equipment loan)",
    )
    bakery.change_payee_answer(loan["match_key"], "equipment")
    assert bakery.told_us()["payees"][0]["category"] == "equipment"
    assert bakery.told_us()["payees"][0]["said"] == "loan repayment (equipment loan)"
    assert [n["text"] for n in told["notes"]] == ["Busy before Christmas"]
    assert told["limits"][0]["label"] == "New oven"

    bakery.remove_declined(0)
    assert any(a.get("payment") == "New oven" for a in bakery.suggested_fixes())
    bakery.remove_owner_note(0)
    assert bakery.owner_notes() == []
    bakery.forget_payee_answer(told["payees"][0]["match_key"])
    assert bakery.told_us()["payees"] == []
