from datetime import date

from aheadly.ai.forecast_engine import expand_scheduled_items
from aheadly.domain import ScheduledItem
from tests.conftest import TODAY


def test_forecast_returns_56_points_with_ordered_percentiles(connected_core):
    forecast = connected_core.get_dashboard().forecast
    assert len(forecast.points) == 56
    assert forecast.points[0].date == TODAY
    assert all(p.balance_p10 <= p.balance_p50 <= p.balance_p90 for p in forecast.points)


def test_recurring_items_expand_inside_the_window():
    items = [
        ScheduledItem("Payroll", -100, date(2026, 11, 20), recurrence="biweekly"),
        ScheduledItem("Rent", -50, date(2026, 11, 15), recurrence="monthly"),
        ScheduledItem("Old", -1, date(2026, 10, 1)),
    ]
    events = expand_scheduled_items(items, TODAY, TODAY.replace(year=2027, month=1, day=3))
    labels = [label for _, _, label in events]
    assert labels.count("Payroll") == 4 and labels.count("Rent") == 2 and "Old" not in labels


def test_backtest_reports_naive_and_main_model(connected_core):
    scores = connected_core.backtest()
    assert "seasonal_naive" in scores and all(v > 0 for v in scores.values())


def test_prophet_gives_the_same_paths_for_the_same_files():
    """Loading the same statement twice shows the same lowest balance (Prophet samples are seeded)."""
    import numpy as np
    import pandas as pd
    import pytest

    pytest.importorskip("prophet")
    from aheadly.ai.models import ProphetModel

    dates = pd.date_range("2026-06-01", periods=120, freq="D")
    flows = np.random.default_rng(1).normal(100, 40, len(dates))
    history = pd.DataFrame({"date": dates, "net_flow": flows})
    runs = []
    for _ in range(2):
        model = ProphetModel(n_paths=50).fit(history)
        runs.append(model.sample_paths(14, 50, np.random.default_rng(7)))
    assert np.allclose(runs[0], runs[1])
