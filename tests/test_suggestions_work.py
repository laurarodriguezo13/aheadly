"""Roadmap R.3a: suggestions the owner can open, change, test again, save, or say no to."""

import pytest

from aheadly.core.actions import ruled_out, suggestion_id
from tests.test_businesses import import_business


@pytest.fixture()
def bakery():
    core = import_business("panaderia-la-esquina", with_one_offs=True)
    core.answer_owner_pay("TRANSF A CTA AHORROS M GOMEZ", True)
    return core


def test_ids_are_stable_and_rules_match_what_they_should():
    adjustments = [{"type": "move_item", "label": "New oven", "new_date": "2026-12-16"}]
    assert suggestion_id(adjustments) == suggestion_id([dict(adjustments[0])])
    rules = [{"kind": "owner_pay"}, {"kind": "move_payment", "label": "New oven"}, {"id": "abc"}]
    assert ruled_out(rules, "owner_pay", "Anything")
    assert ruled_out(rules, "move_payment", "New oven") and not ruled_out(rules, "move_payment", "Rent")
    assert ruled_out(rules, "pair", sid="abc") and not ruled_out(rules, "price")


def test_every_suggestion_is_listed_once_with_where_it_comes_from(bakery):
    found = bakery.all_suggestions()
    assert found and len({s["id"] for s in found}) == len(found)
    first = found[0]
    assert first["source"] == "Warning: your cash could run out"
    assert first["action"]["label"].startswith("Move New oven")
    assert any(s["context"] for s in found)  # the bad surprises' fixes keep their surprise


def test_the_owner_can_change_a_suggestion_and_test_it_again(bakery):
    move = next(s["action"] for s in bakery.all_suggestions() if s["action"]["kind"] == "move_payment")
    as_suggested = bakery.test_suggestion(move["adjustments"])["impact"]
    sooner = [{**move["adjustments"][0], "new_date": "2026-11-21"}]  # a week later only
    mine = bakery.test_suggestion(sooner)["impact"]
    assert mine["lowest_after"] != as_suggested["lowest_after"]
    assert mine["lowest_before"] == as_suggested["lowest_before"]
    assert bakery.saved_scenarios() == []  # testing keeps nothing


def test_not_for_me_on_one_payment_and_on_a_whole_kind(bakery):
    oven = next(a for a in bakery.suggested_fixes() if a.get("payment") == "New oven")
    rule = bakery.decline_suggestion(oven, "wont_agree", "the supplier needs it by the 14th")
    assert rule["kind"] == "move_payment" and rule["label"] == "New oven"
    assert all(a.get("payment") != "New oven" for a in bakery.suggested_fixes())
    alert = bakery.get_alerts()[0]
    assert all(a.get("payment") != "New oven" for a in alert.actions)  # the alert's own list too

    bakery.decline_suggestion({"kind": "owner_pay", "label": "x", "adjustments": []}, "cant_lower_pay")
    assert all(a["kind"] != "owner_pay" for s in bakery.all_suggestions() for a in [s["action"]])
    assert len(bakery.declined_suggestions()) == 2

    bakery.bring_back_suggestions()
    assert any(a.get("payment") == "New oven" for a in bakery.suggested_fixes())


def test_saving_a_bad_surprise_fix_saves_only_the_fix(bakery):
    fix = next(s for s in bakery.all_suggestions() if s["context"])
    bakery.save_suggestion(fix["action"]["adjustments"], fix["action"]["label"])
    saved = bakery.saved_scenarios()[0]
    assert saved["saved_as_plan"]
    assert all(a.get("type") != "revenue_change" or a.get("weeks") is None for a in saved["adjustments"])


def test_a_thing_we_noticed_can_be_set_aside():
    cafe = import_business("cafe-la-tertulia", with_one_offs=True)
    first = cafe.noticed_cards()[0]["type"]
    cafe.set_aside_insight(first, "known")
    assert first not in {c["type"] for c in cafe.noticed_cards()}
    assert first in {c["type"] for c in cafe.insight_cards()}  # still known to the chat and the checks
    with pytest.raises(ValueError):
        cafe.set_aside_insight(first, "meh")
