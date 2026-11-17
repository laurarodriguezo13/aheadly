"""Review after Phase R (2026-11-16): what the full check of the code and the live site found."""

import pytest

from aheadly.ai.insight_translator import tidy_money
from aheadly.data.repository import Repository
from tests.test_businesses import import_business


@pytest.fixture(scope="module")
def bakery():
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    core.answer_owner_pay("TRANSF A CTA AHORROS M GOMEZ", True)
    return core


def test_amounts_in_the_ais_words_read_like_ours():
    """Issue 31: Gemini wrote "-$1058" in the alert."""
    assert tidy_money("down to -$1058 on Dec 15") == "down to -$1,058 on Dec 15"
    assert tidy_money("$-748 and $12345.50") == "-$748 and $12,345.50"
    assert tidy_money("$1,058 in 2026, $999") == "$1,058 in 2026, $999"


def test_the_owners_pay_is_never_called_by_the_banks_wording(bakery):
    pay = [a for a in bakery.suggested_fixes() if a["kind"] == "owner_pay"]
    pay += [a for c in bakery.insight_cards() for a in c["actions"] if a.get("kind") == "owner_pay"]
    assert pay and all(a["detail"].startswith("Your own pay:") for a in pay)
    assert bakery.safe_numbers()["owner_pay"]["payment"] == "Your own pay"


def test_a_change_the_owner_ruled_out_is_not_offered_even_as_advice(bakery):
    """Issue 30: after "I can't lower my pay", the pay insight still said "Take a little less"."""
    card = next(c for c in bakery.insight_cards() if c["type"] == "owner_pay_high")
    assert any(a.get("key") == "lower_owner_pay_for_a_while" for a in card["actions"])
    bakery.keep_anything_else([{"kind": "owner_pay", "quote": "I can't lower my pay"}], [])
    try:
        card = next(c for c in bakery.insight_cards() if c["type"] == "owner_pay_high")
        assert all(a.get("key") != "lower_owner_pay_for_a_while" for a in card["actions"])
    finally:
        bakery.bring_back_suggestions()


def test_a_cash_shortfall_is_listed_before_a_doubled_charge():
    """The café's shortfall 8 weeks out (low) was listed under a $172 doubled charge (medium)."""
    repo = Repository(":memory:")
    business = repo.create_business(name="Café", owner_name="", city="", low_cash_line=1500)
    repo.add_alert(business.id, None, "duplicate_charge", "medium", 0, {}, "Check this charge", "", [])
    repo.add_alert(business.id, None, "shortfall", "low", 8, {}, "Heads up", "", [])
    repo.add_alert(business.id, None, "unusual_charge", "low", 0, {}, "Check this one", "", [])
    assert [a.type for a in repo.list_alerts(business.id)] == [
        "shortfall",
        "duplicate_charge",
        "unusual_charge",
    ]
