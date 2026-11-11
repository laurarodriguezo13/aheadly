"""Every visitor starts with an empty app; the shared mode keeps one database."""

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import StubClient
from aheadly.ai.models import SeasonalNaiveModel
from aheadly.config import Settings
from aheadly.core.session import new_core
from aheadly.data.connectors.demo_connector import DemoConnector
from tests.conftest import TODAY


def _engine() -> ForecastEngine:
    return ForecastEngine(SeasonalNaiveModel(), n_paths=50)


def test_per_visitor_data_is_on_by_default():
    assert Settings().per_visitor_data is True


def test_each_visitor_starts_with_an_empty_app():
    settings = Settings(llm_provider="stub", per_visitor_data=True)
    engine = _engine()
    maria = new_core(settings, engine, llm=StubClient(TODAY), today=TODAY)
    professor = new_core(settings, engine, llm=StubClient(TODAY), today=TODAY)

    maria.connect(DemoConnector(TODAY))

    assert maria.status().connected
    assert not professor.status().connected


def test_shared_mode_uses_one_database_file(tmp_path):
    settings = Settings(llm_provider="stub", per_visitor_data=False, db_path=tmp_path / "shared.db")
    engine = _engine()
    first = new_core(settings, engine, llm=StubClient(TODAY), today=TODAY)
    second = new_core(settings, engine, llm=StubClient(TODAY), today=TODAY)

    first.connect(DemoConnector(TODAY))

    assert second.status().connected
