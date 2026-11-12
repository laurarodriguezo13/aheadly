"""Roadmap 1.3: the forecast starts where the statement ends, the balance must add up,
and the same bank line is never counted twice."""

from datetime import date, timedelta

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.ai.llm_client import StubClient
from aheadly.ai.models import SeasonalNaiveModel
from aheadly.config import Settings
from aheadly.core.app_core import AppCore
from aheadly.data.connectors.csv_connector import CsvConnector
from aheadly.data.repository import Repository

HEADER = "Date,Description,Debit,Credit,Balance\n"
ADDS_UP = (
    HEADER
    + "2026-11-02,CARD SALES,,1500,9000\n"
    + "2026-11-03,PAYROLL,800,,8200\n"
    + "2026-11-04,CARD SALES,,300,8500\n"
)


def _ids(text: str, balance: float | None = None) -> list[str]:
    return [t.external_id for t in CsvConnector(text, balance, "statement.csv").sync().transactions]


def _statement_ending(last_day: date, days: int = 40) -> str:
    rows, balance = [HEADER.strip()], 5000.0
    for i in range(days, -1, -1):
        balance += 100
        rows.append(f"{last_day - timedelta(days=i)},CARD SALES,,100,{balance}")
    return "\n".join(rows) + "\n"


def _live_core() -> AppCore:
    """Like the shared fixture, but with no fixed date: it follows the real calendar."""
    settings = Settings(demo_mode=True, llm_provider="stub", db_path=":memory:")
    return AppCore(
        Repository(":memory:"),
        ForecastEngine(SeasonalNaiveModel(), n_paths=200),
        settings,
        llm=StubClient(date.today()),
    )


# ------------------------------------------------------------- the same line, the same id
def test_uploading_the_same_statement_twice_gives_the_same_ids():
    assert _ids(ADDS_UP) == _ids(ADDS_UP)


def test_overlapping_statements_share_the_ids_of_the_lines_they_both_have():
    later = (
        HEADER + "2026-11-03,PAYROLL,800,,8200\n2026-11-04,CARD SALES,,300,8500\n2026-11-05,RENT,900,,7600\n"
    )
    assert set(_ids(ADDS_UP)) & set(_ids(later)) == set(_ids(ADDS_UP)[1:])


def test_two_identical_lines_on_the_same_day_are_both_kept():
    twice = "Date,Description,Amount\n2026-11-02,CARD SALES,50\n2026-11-02,CARD SALES,50\n"
    ids = _ids(twice, balance=1000)
    assert len(ids) == 2 and len(set(ids)) == 2


def test_reimporting_adds_nothing_new():
    repo = Repository(":memory:")
    business = repo.create_business(name="Test", owner_name="", city="", low_cash_line=2000.0)
    account = repo.add_account(business.id, "csv", "Imported file", 8500.0)
    transactions = CsvConnector(ADDS_UP, None, "statement.csv").sync().transactions
    assert repo.add_transactions(business.id, account, transactions) == 3
    assert repo.add_transactions(business.id, account, transactions) == 0


# ------------------------------------------------------------- newest-first statements
def test_newest_first_statement_closes_on_its_newest_line():
    newest_first = (
        HEADER
        + "2026-11-04,CARD SALES,,300,8500\n"
        + "2026-11-04,SUPPLIER,200,,8200\n"
        + "2026-11-03,PAYROLL,800,,8400\n"
        + "2026-11-02,CARD SALES,,1500,9200\n"
    )
    connector = CsvConnector(newest_first, None, "statement.csv")
    assert connector.sync().balance == 8500
    assert connector.balance_breaks == 0


# ------------------------------------------------------------- the balance must add up
def test_a_statement_that_adds_up_has_no_breaks():
    connector = CsvConnector(ADDS_UP, None, "statement.csv")
    connector.sync()
    assert (connector.balance_breaks, connector.first_break) == (0, None)


def test_a_missing_row_shows_up_as_a_break():
    missing_payroll = HEADER + "2026-11-02,CARD SALES,,1500,9000\n2026-11-04,CARD SALES,,300,8500\n"
    connector = CsvConnector(missing_payroll, None, "statement.csv")
    connector.sync()
    assert connector.balance_breaks == 1
    assert connector.first_break == date(2026, 11, 4)


def test_without_a_balance_column_there_is_nothing_to_check():
    connector = CsvConnector("Date,Description,Amount\n2026-11-02,CARD SALES,50\n", 1000, "s.csv")
    connector.sync()
    assert (connector.balance_breaks, connector.first_break) == (0, None)


def test_connector_reports_where_the_statement_ends():
    connector = CsvConnector(ADDS_UP, None, "statement.csv")
    connector.sync()
    assert connector.statement_end == date(2026, 11, 4)


# ------------------------------------------------------------- the forecast starts where the statement ends
def test_an_old_statement_moves_the_forecast_start_back():
    last = date.today() - timedelta(days=20)
    core = _live_core()
    core.connect(CsvConnector(_statement_ending(last), None, "statement.csv"))
    assert core.statement_end() == last
    assert core.today == last + timedelta(days=1)
    assert core.statement_lag_days() == 19
    assert core.get_dashboard().forecast.points[0].date == last + timedelta(days=1)


def test_a_statement_ending_yesterday_keeps_today():
    core = _live_core()
    core.connect(CsvConnector(_statement_ending(date.today() - timedelta(days=1)), None, "statement.csv"))
    assert core.today == date.today()
    assert core.statement_lag_days() == 0


def test_an_unreadable_line_is_reported_once_not_as_a_break_too():
    garbled = (
        HEADER
        + "2026-11-02,CARD SALES,,1500,9000\n2026-11-03,PAYROLL,8#0,,8200\n2026-11-04,CARD SALES,,300,8500\n"
    )
    connector = CsvConnector(garbled, None, "statement.csv")
    connector.sync()
    assert connector.skipped_rows == 1
    assert (connector.balance_breaks, connector.first_break) == (0, None)
