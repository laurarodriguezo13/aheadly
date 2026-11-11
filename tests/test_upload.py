"""Upload-only onboarding: a bank statement plus an optional list of upcoming payments."""

from datetime import date, timedelta

import pytest

from aheadly.data.connectors.csv_connector import CsvConnector, read_upcoming_payments
from tests.conftest import TODAY

STATEMENT = (
    "Date,Description,Debit,Credit,Balance\n2026-11-02,CARD SALES,,1500,9000\n2026-11-03,PAYROLL,800,,8200\n"
)
UPCOMING = "Date,Description,Amount\n2026-11-20,New oven,-7500\n2026-12-17,Cafe Azul order,5500\n"


def _long_statement(days: int = 60) -> str:
    """A small bakery: 700 in every day, a 2,000 supplier payment every Monday."""
    rows, balance = ["Date,Description,Debit,Credit,Balance"], 5000.0
    for i in range(days, 0, -1):
        day = TODAY - timedelta(days=i)
        balance += 700
        rows.append(f"{day},CARD SALES,,700,{balance}")
        if day.weekday() == 0:
            balance -= 2000
            rows.append(f"{day},SUPPLIER,2000,,{balance}")
    return "\n".join(rows) + "\n"


def test_balance_comes_from_the_statement_when_not_typed():
    assert CsvConnector(STATEMENT, None, "statement.csv").sync().balance == 8200


def test_typed_balance_wins_over_the_file():
    assert CsvConnector(STATEMENT, 9100, "statement.csv").sync().balance == 9100


def test_no_balance_anywhere_is_a_clear_error():
    no_balance = "Date,Description,Amount\n2026-11-02,CARD SALES,1500\n"
    with pytest.raises(ValueError, match="balance"):
        CsvConnector(no_balance, None, "statement.csv").sync()


def test_upcoming_payments_file_becomes_planned_items():
    items = read_upcoming_payments(UPCOMING.encode(), "upcoming.csv")
    assert [(i.label, i.amount, i.due_date, i.kind) for i in items] == [
        ("New oven", -7500.0, date(2026, 11, 20), "bill"),
        ("Cafe Azul order", 5500.0, date(2026, 12, 17), "receivable"),
    ]


def test_upload_with_upcoming_payments_reaches_the_forecast(core):
    business = {"name": "Test Bakery", "owner_name": "Ana", "city": "", "low_cash_line": 2000.0}
    connector = CsvConnector(
        _long_statement(),
        None,
        "statement.csv",
        business_profile=business,
        upcoming=UPCOMING.encode(),
        upcoming_filename="upcoming.csv",
    )
    core.connect(connector)

    assert core.status().business.name == "Test Bakery"
    assert "New oven" in [label for _, _, label in core.get_dashboard().forecast.scheduled]
