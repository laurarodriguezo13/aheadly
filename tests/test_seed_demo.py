from aheadly.data.seed_demo import DEMO_OPENING_BALANCE, build_demo_dataset
from tests.conftest import TODAY


def test_seed_is_deterministic():
    a, b = build_demo_dataset(TODAY), build_demo_dataset(TODAY)
    assert [t.amount for t in a.transactions] == [t.amount for t in b.transactions]


def test_seed_covers_twelve_months_with_expected_weekly_totals():
    dataset = build_demo_dataset(TODAY)
    weekly_net = sum(t.amount for t in dataset.transactions) / 52
    assert dataset.opening_balance == DEMO_OPENING_BALANCE == 8200
    assert (TODAY - min(t.date for t in dataset.transactions)).days >= 360
    assert 0 < weekly_net < 600, "ordinary weeks should net a few hundred dollars"


def test_seed_has_the_oven_and_the_week_five_cluster():
    labels = {item.label for item in build_demo_dataset(TODAY).scheduled_items}
    assert "New oven" in labels and "Inventory" in labels
    assert any("Supplier payment" in label for label in labels)


def test_canonical_story_shortfall_then_safe_after_moving_oven(connected_core):
    forecast = connected_core.get_dashboard().forecast
    assert -4400 <= forecast.lowest.balance_p50 <= -3600  # about -4,000 within 10%
    assert 4 <= (forecast.lowest.date - TODAY).days // 7 + 1 <= 6  # in about 5 weeks

    result = connected_core.run_what_if(
        [{"type": "move_item", "label": "oven", "new_date": "2026-12-31"}], "Oven next month"
    )
    assert result.scenario.lowest.balance_p50 > 3000
    assert result.stays_above_line
