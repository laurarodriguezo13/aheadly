import json

import pytest

from aheadly.ai.tools import TOOL_SCHEMAS, ToolDispatcher

SAMPLE_ARGS = {
    "get_cash_summary": {},
    "get_forecast": {"weeks": 4},
    "get_upcoming_outflows": {"weeks": 8},
    "get_transactions": {"limit": 5, "category": "sales"},
    "get_alerts": {},
    "run_scenario": {
        "name": "t",
        "adjustments": [{"type": "move_item", "label": "oven", "new_date": "2026-12-31"}],
    },
}


@pytest.mark.parametrize("schema", TOOL_SCHEMAS, ids=lambda s: s["name"])
def test_every_tool_returns_json_serialisable_data(connected_core, schema):
    result = ToolDispatcher(connected_core).dispatch(schema["name"], SAMPLE_ARGS[schema["name"]])
    assert "error" not in result
    json.dumps(result)


def test_unknown_tool_and_bad_arguments_return_an_error_payload(connected_core):
    dispatcher = ToolDispatcher(connected_core)
    assert "error" in dispatcher.dispatch("fly_to_moon", {})
    assert "error" in dispatcher.dispatch("run_scenario", {"name": "x", "adjustments": [{"type": "nope"}]})
