"""Shared fixtures: an offline App Core (in-memory SQLite, naive model, stub LLM, fixed date)."""

from datetime import date

import pytest

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import StubClient
from aheadly.ai.models import SeasonalNaiveModel
from aheadly.config import Settings
from aheadly.core.app_core import AppCore
from aheadly.data.connectors.demo_connector import DemoConnector
from aheadly.data.repository import Repository

TODAY = date(2026, 11, 9)


@pytest.fixture
def core() -> AppCore:
    settings = Settings(llm_provider="stub", db_path=":memory:")
    return AppCore(
        Repository(":memory:"),
        ForecastEngine(SeasonalNaiveModel(), n_paths=200),
        settings,
        llm=StubClient(TODAY),
        today=TODAY,
    )


@pytest.fixture
def connected_core(core: AppCore) -> AppCore:
    core.connect(DemoConnector(TODAY))
    return core


def pytest_terminal_summary(terminalreporter):
    """A scorecard of the test businesses (tests/test_businesses.py) at the end of every run."""
    rows: dict[str, dict[str, int]] = {}
    for outcome in ("passed", "failed", "xfailed", "xpassed"):
        for report in terminalreporter.stats.get(outcome, []):
            nodeid = getattr(report, "nodeid", "")
            if "test_businesses.py" not in nodeid or getattr(report, "when", "call") != "call":
                continue
            business = nodeid.split("[", 1)[1].split("/")[0].rstrip("]")
            rows.setdefault(business, {}).setdefault(outcome, 0)
            rows[business][outcome] += 1
    if not rows:
        return
    terminalreporter.section("test businesses")
    terminalreporter.write_line(f"{'business':26} {'pass':>5} {'to do':>6} {'FAIL':>5}")
    for business in sorted(rows):
        r = rows[business]
        failed = r.get("failed", 0) + r.get("xpassed", 0)
        terminalreporter.write_line(
            f"{business:26} {r.get('passed', 0):>5} {r.get('xfailed', 0):>6} {failed:>5}"
        )
    terminalreporter.write_line(
        "to do = waiting for a roadmap item (see PENDING in tests/test_businesses.py)"
    )
