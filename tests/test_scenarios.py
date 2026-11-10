import pytest

from aheadly.ai.scenarios import parse_adjustment


def _lowest(core, adjustments):
    return core.run_what_if(adjustments, "t").scenario.lowest.balance_p50


def test_one_time_expense_lowers_the_lowest_balance(connected_core):
    base = connected_core.get_dashboard().forecast.lowest.balance_p50
    assert (
        _lowest(connected_core, [{"type": "one_time_expense", "amount": 1000, "date": "2026-11-12"}]) < base
    )


def test_remove_item_raises_the_lowest_balance(connected_core):
    base = connected_core.get_dashboard().forecast.lowest.balance_p50
    assert _lowest(connected_core, [{"type": "remove_item", "label": "oven"}]) > base + 7000


def test_revenue_change_moves_the_forecast_in_the_right_direction(connected_core):
    up = _lowest(connected_core, [{"type": "revenue_change", "percent": 10}])
    down = _lowest(connected_core, [{"type": "revenue_change", "percent": -10}])
    assert up > down


def test_recurring_change_and_collect_early(connected_core):
    base = connected_core.get_dashboard().forecast.lowest.balance_p50
    assert (
        _lowest(connected_core, [{"type": "recurring_change", "label": "Payroll", "amount_delta": -500}])
        < base
    )
    early = _lowest(
        connected_core, [{"type": "collect_early", "label": "Café Azul", "new_date": "2026-12-10"}]
    )
    assert early > base


def test_invalid_adjustments_are_rejected():
    with pytest.raises(ValueError):
        parse_adjustment({"type": "teleport"})
    with pytest.raises(ValueError):
        parse_adjustment({"type": "one_time_expense", "amount": -5})
    with pytest.raises(ValueError):
        parse_adjustment({"type": "move_item", "new_date": "2026-12-01"})
