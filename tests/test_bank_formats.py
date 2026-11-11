"""Latin American bank files: day/month dates, "1.250,00" amounts, and no silent zeros."""

from datetime import date

import pandas as pd

from aheadly.data.connectors.csv_connector import CsvConnector, parse_amounts, parse_dates


def test_day_first_dates_are_read_as_day_month_year():
    parsed = parse_dates(pd.Series(["03/11/2026", "15/11/2026"]))
    assert [d.date() for d in parsed] == [date(2026, 11, 3), date(2026, 11, 15)]


def test_month_first_dates_still_work_when_clear():
    parsed = parse_dates(pd.Series(["11/03/2026", "11/15/2026"]))
    assert [d.date() for d in parsed] == [date(2026, 11, 3), date(2026, 11, 15)]


def test_iso_dates_are_unchanged():
    assert parse_dates(pd.Series(["2026-11-03"]))[0].date() == date(2026, 11, 3)


def test_amounts_in_latin_american_and_us_formats():
    values = ["1.250,00", "1,250.00", "$ 2.000", "(900,50)", "850,5", "-75.25", "12.500"]
    assert list(parse_amounts(pd.Series(values))) == [1250.0, 1250.0, 2000.0, -900.5, 850.5, -75.25, 12500.0]


def test_unreadable_rows_are_skipped_and_counted_not_turned_into_zero():
    statement = 'Fecha,Descripción,Débito,Crédito,Saldo\n03/11/2026,PAGO ARRIENDO,"1.250,00",,"8.000,00"\n15/11/2026,ABONO,,abc,"8.000,00"\n'
    connector = CsvConnector(statement, None, "extracto.csv")
    payload = connector.sync()

    assert [(t.date, t.amount) for t in payload.transactions] == [(date(2026, 11, 3), -1250.0)]
    assert connector.skipped_rows == 1
    assert payload.balance == 8000.0
