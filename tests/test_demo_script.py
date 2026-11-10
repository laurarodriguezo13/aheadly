"""Functional test: the demo script from the spec (storyboard frames 1 to 6), offline."""

from aheadly.data.connectors.demo_connector import DemoConnector
from tests.conftest import TODAY


def test_frame_1_fresh_start_has_no_data(core):
    assert core.status().connected is False


def test_frames_2_to_6_connect_alert_whatif_save_plan(core):
    core.connect(DemoConnector(TODAY))  # frame 2: connect once
    dash = core.get_dashboard()  # frame 3: always watching
    assert dash.balance == 8200 and dash.forecast is not None

    alerts = core.get_alerts()  # frame 4: early warning
    assert len(alerts) == 1 and alerts[0].type == "shortfall" and alerts[0].severity in ("medium", "high")
    assert core.unread_alert_count() == 1
    assert len(alerts[0].actions) >= 2 and len(alerts[0].facts["top_outflows"]) == 3

    answer = core.ask("What if I buy the new oven next month instead?")  # frame 5: ask in plain words
    assert "run_scenario" in answer.tool_names and answer.scenario is not None
    assert answer.scenario.stays_above_line and "safe" in answer.text.lower()

    summary = core.save_plan(answer.scenario)  # frame 6: act with confidence
    assert summary.alerts_resolved == 1 and core.get_alerts() == []
    assert core.get_dashboard().forecast.lowest.balance_p50 > 2000


def test_daily_check_updates_instead_of_duplicating_alerts(connected_core):
    connected_core.run_daily_check(force=True)
    connected_core.run_daily_check(force=True)
    assert len(connected_core.get_alerts()) == 1
