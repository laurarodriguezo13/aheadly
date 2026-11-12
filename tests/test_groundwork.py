"""Roadmap 1.4 groundwork: a database that upgrades itself, a business profile, planned items that
remember where they came from, and "today" in the owner's own time zone."""

import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import StubClient
from aheadly.ai.models import SeasonalNaiveModel
from aheadly.config import Settings
from aheadly.core.app_core import AppCore
from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.data.repository import MIGRATIONS, SCHEMA_PATH, Repository
from aheadly.domain import ScheduledItem


def _columns(repo: Repository, table: str) -> set[str]:
    return {row["name"] for row in repo._conn.execute(f"PRAGMA table_info({table})")}


def _repo_with_business() -> tuple[Repository, int]:
    repo = Repository(":memory:")
    business = repo.create_business(name="Test", owner_name="", city="", low_cash_line=2000.0)
    return repo, business.id


def _live_core() -> AppCore:
    settings = Settings(demo_mode=True, llm_provider="stub", db_path=":memory:")
    return AppCore(
        Repository(":memory:"),
        ForecastEngine(SeasonalNaiveModel(), n_paths=200),
        settings,
        llm=StubClient(date.today()),
    )


# ------------------------------------------------------------- migrations
def test_a_new_database_is_at_the_latest_version_with_the_new_columns():
    repo = Repository(":memory:")
    assert repo.schema_version() == len(MIGRATIONS)
    assert {"status", "certainty", "likelihood", "user_edited", "match_key", "paused"} <= _columns(
        repo, "scheduled_items"
    )
    assert {"scheduled_item_id", "category_source", "is_internal_transfer"} <= _columns(repo, "transactions")
    assert {"kind", "currency"} <= _columns(repo, "accounts")
    assert "chance_below_line" in _columns(repo, "forecast_runs")
    for table in ("business_profile", "payee_rules", "insights", "uploaded_files"):
        assert _columns(repo, table), table


def test_an_old_database_file_upgrades_and_keeps_its_data(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(SCHEMA_PATH.read_text())
    old.execute("INSERT INTO businesses (name, owner_name, city) VALUES ('Old Bakery', 'Ana', 'Cali')")
    old.execute(
        "INSERT INTO scheduled_items (business_id, kind, label, amount, due_date, source) "
        "VALUES (1, 'rent', 'Rent', -900, '2026-12-15', 'csv')"
    )
    old.commit()
    old.close()

    repo = Repository(path)
    assert repo.schema_version() == len(MIGRATIONS)
    assert repo.get_business().name == "Old Bakery"
    [rent] = repo.list_scheduled_items(1)
    assert (rent.label, rent.status, rent.certainty, rent.likelihood) == ("Rent", "user", "confirmed", 1.0)


def test_opening_an_up_to_date_database_again_changes_nothing(tmp_path):
    path = tmp_path / "app.db"
    Repository(path).close()
    assert Repository(path).schema_version() == len(MIGRATIONS)


# ------------------------------------------------------------- business profile
def test_profile_starts_empty_and_keeps_what_is_saved():
    repo, business_id = _repo_with_business()
    assert repo.get_profile(business_id) == {}
    repo.save_profile(business_id, {"business_type": "bakery", "employees": 6})
    repo.save_profile(business_id, {"employees": 7, "time_zone": "America/Bogota"})
    assert repo.get_profile(business_id) == {
        "business_type": "bakery",
        "employees": 7,
        "time_zone": "America/Bogota",
    }


# ------------------------------------------------------------- planned items remember where they came from
def test_planned_items_keep_their_origin_and_certainty():
    repo, business_id = _repo_with_business()
    detected = ScheduledItem(
        label="Rent",
        amount=-900,
        due_date=date(2026, 12, 15),
        kind="rent",
        recurrence="monthly",
        source="statement",
        status="detected",
        certainty="maybe",
        likelihood=0.8,
        category="rent",
        match_key="arriendo local",
    )
    repo.add_scheduled_items(business_id, [detected])
    [saved] = repo.list_scheduled_items(business_id)
    assert (saved.status, saved.certainty, saved.likelihood) == ("detected", "maybe", 0.8)
    assert (saved.category, saved.match_key, saved.user_edited, saved.paused) == (
        "rent",
        "arriendo local",
        False,
        False,
    )


def test_start_over_clears_the_new_tables_too():
    repo, business_id = _repo_with_business()
    repo.save_profile(business_id, {"employees": 6})
    repo.reset()
    assert repo.get_business() is None
    assert repo._conn.execute("SELECT COUNT(*) FROM business_profile").fetchone()[0] == 0


# ------------------------------------------------------------- today in the owner's time zone
def test_today_follows_the_owners_time_zone():
    for zone in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):  # UTC+14 and UTC-11: never the same day
        core = _live_core()
        core.set_time_zone(zone)
        assert core.today == datetime.now(ZoneInfo(zone)).date()


def test_an_unknown_time_zone_is_ignored():
    core = _live_core()
    core.set_time_zone("Not/AZone")
    assert core.time_zone is None
    assert core.today == date.today()


def test_the_time_zone_is_kept_with_the_business_after_upload():
    core = _live_core()
    core.set_time_zone("America/Bogota")
    yesterday = datetime.now(ZoneInfo("America/Bogota")).date() - timedelta(days=1)
    lines = [f"{yesterday - timedelta(days=i)},CARD SALES,100,{5000 - 100 * i}" for i in range(20, -1, -1)]
    statement = "Date,Description,Amount,Balance\n" + "\n".join(lines) + "\n"
    core.connect(CsvConnector(statement, None, "statement.csv"))
    business = core.status().business
    assert core.repo.get_profile(business.id)["time_zone"] == "America/Bogota"
    assert core.statement_lag_days() == 0
