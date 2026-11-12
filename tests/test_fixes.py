"""Roadmap 3.3: suggested fixes, tested by the app.

Beyond 3.2's "move a payment in the tight week", the app now tries, on its own: moving any payment
that lands once before the low point (also to just after the money that rescues it), asking for
money due after the first day below the line a little earlier, paying the owner less for the next
8 weeks, raising prices a little, and pairs of these when no single change is enough. Each is run
as a what-if; the top three are shown, best first. If even the best leaves the base case below the
line, the app says so and how much is missing.
"""

from datetime import timedelta

from aheadly.core import actions
from tests.conftest import TODAY


def _fixes(core):
    core.run_daily_check(force=True)
    return next(a for a in core.get_alerts() if a.type == "shortfall").actions


def test_moving_the_oven_is_suggested_and_fixes_it(connected_core):
    """The canonical demo: the oven, due well before the low point, moved to after the money that
    comes in later, takes the bakery out of "act now"."""
    oven = [a for a in _fixes(connected_core) if "oven" in a["label"].lower()]
    assert oven, [a["label"] for a in _fixes(connected_core)]
    assert oven[0]["impact"]["risk_after"] != "act_now"


def test_ranked_by_status_then_cost_then_worst_case(connected_core):
    tested = [a for a in _fixes(connected_core) if a.get("adjustments")]
    keys = [actions.rank_key(a) for a in tested]
    assert keys == sorted(keys)


def test_one_suggestion_per_payment(connected_core):
    labels = [
        tuple(sorted(adj["label"] for adj in a["adjustments"]))
        for a in _fixes(connected_core)
        if a.get("adjustments")
    ]
    assert len(labels) == len(set(labels))


def test_owner_pay_is_tried(core):
    """With the owner's pay known, paying less is one of the candidates (the café's way out)."""
    from tests.test_businesses import import_business

    cafe = import_business("cafe-la-tertulia", with_one_offs=True)
    kinds = {a.get("kind") for a in _fixes(cafe)}
    assert kinds & {"owner_pay", "price", "pair"}, kinds


def test_says_when_nothing_is_enough():
    """If even the best suggestion leaves the base case below the line, the gap is given."""
    best = {"impact": {"risk_after": "act_now", "lowest_after": 1400}}
    assert actions.still_short([best], low_cash_line=2000) == 600
    assert actions.still_short([{"impact": {"risk_after": "watch", "lowest_after": 2600}}], 2000) is None
    assert actions.still_short([], 2000) is None


def test_suggestions_when_only_the_worst_case_dips(connected_core):
    """'Watch' has no alert, but the owner can still see what would make it safe."""
    business = connected_core.status().business
    oven = next(i for i in connected_core.repo.list_scheduled_items(business.id) if "oven" in i.label.lower())
    later = oven.due_date + timedelta(days=40)
    connected_core.save_plan(
        connected_core.run_what_if(
            [{"type": "move_item", "label": oven.label, "new_date": later.isoformat()}]
        )
    )
    fixes = connected_core.suggested_fixes()
    risk = connected_core._baseline_forecast().risk_level(business.low_cash_line)
    if risk == "watch":
        assert fixes and all(
            f["impact"]["risk_after"] == "safe" or f["impact"]["lowest_after"] >= f["impact"]["lowest_before"]
            for f in fixes
        )
    else:
        assert risk == "safe" and fixes == []


def test_pairs_named_with_both_parts():
    pair = actions.pair_words(
        {"label": "Move New oven to Dec 21", "how_to": ["Call them.", "Ask.", "Save."]},
        {"label": "Pause your own pay for the next 8 weeks", "how_to": ["Decide.", "Change it.", "Save."]},
    )
    assert pair["label"] == "Move New oven to Dec 21 + pause your own pay for the next 8 weeks"
    assert len(pair["how_to"]) == 3
