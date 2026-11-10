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
    settings = Settings(demo_mode=True, llm_provider="stub", db_path=":memory:")
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
