"""DECISIONS #64: a supplier paid every week, a different amount each time, sits in the normal week the
forecast learns from. The owner can plan it on its own (then change it, pause it or start it again
later, like any regular payment) and put it back."""

from datetime import timedelta

import pytest

from tests.test_businesses import import_business


@pytest.fixture(scope="module")
def hardware():
    return import_business("ferreteria-don-perno", with_one_offs=True)


def _supplier(core):
    return next(p for p in core.weekly_payees() if "distribuidora" in p["match_key"])


def test_the_weekly_supplier_is_offered_and_money_in_and_fees_are_not(hardware):
    payees = hardware.weekly_payees()
    supplier = _supplier(hardware)
    assert supplier["per_week"] < -1000 and supplier["how_often"] == "weekly"
    assert all(p["direction"] == "out" for p in payees)  # weekly cash deposits are the normal week
    assert not any("consignacion" in p["match_key"] for p in payees)


def test_a_what_if_on_it_says_how_to_plan_it_first(hardware):
    supplier = _supplier(hardware)
    with pytest.raises(ValueError, match="Plan it on its own"):
        hardware._scenario([{"type": "remove_item", "label": supplier["label"]}])


def test_plan_it_change_it_and_put_it_back():
    core = import_business("ferreteria-don-perno", with_one_offs=True)
    supplier = _supplier(core)
    start = core.get_dashboard().forecast.lowest_with_today()[0]
    lines_before = core.repo.daily_net_flow(core._business().id, exclude_linked=True)["net_flow"].sum()

    effect = core.plan_weekly_payee(supplier["match_key"])
    assert effect["before"] == round(start)
    item = next(
        i for i in core.repo.list_scheduled_items(core._business().id) if i.match_key == supplier["match_key"]
    )
    assert item.recurrence == "weekly" and item.amount == pytest.approx(supplier["per_week"], abs=0.01)
    assert item.user_edited and item.due_date >= core.today
    # its past lines left the normal week (the forecast puts it on its own days now)
    lines_after = core.repo.daily_net_flow(core._business().id, exclude_linked=True)["net_flow"].sum()
    assert lines_after > lines_before + 1000
    assert supplier["match_key"] not in {p["match_key"] for p in core.weekly_payees()}
    row = next(r for r in core.forecast_basis()["regular"] if r["id"] == item.id)
    assert row["weekly_payee"] and row["varies"]

    # a new upload (detection runs again) keeps it planned and its lines linked
    core._detect_recurring(core._business().id)
    again = core.repo.daily_net_flow(core._business().id, exclude_linked=True)["net_flow"].sum()
    assert again == pytest.approx(lines_after)

    # now the chat can test it, and the owner can buy nothing from it for 6 weeks
    assert core._scenario([{"type": "remove_item", "label": item.label}]).scenario
    later = core.update_plan_item(item.id, due_date=core.today + timedelta(weeks=6))
    assert later["after"] > later["before"]

    core.back_to_normal_week(item.id)
    assert supplier["match_key"] in {p["match_key"] for p in core.weekly_payees()}
    assert not any(
        i.match_key == supplier["match_key"] for i in core.repo.list_scheduled_items(core._business().id)
    )
    assert core.get_dashboard().forecast.lowest_with_today()[0] == pytest.approx(start, abs=1)
