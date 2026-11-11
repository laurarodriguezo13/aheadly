"""Real bank exports, found by the independent test businesses: semicolons, Windows encoding,
preamble lines above the header, Spanish month names and other header names."""

from datetime import date

from aheadly.data.connectors.csv_connector import CsvConnector, parse_dates
import pandas as pd


def _sync(content: bytes | str, balance=None, name="extracto.csv"):
    connector = CsvConnector(content, balance, name)
    return connector, connector.sync()


def test_semicolon_separated_file_with_decimal_commas():
    text = "Fecha;Descripción;Valor;Saldo\n10/11/2026;GMF 4X1000;-0,82;8.200,00\n09/11/2026;ABONO VENTAS;407,90;8.200,82\n"
    connector, payload = _sync(text)
    assert sorted(t.amount for t in payload.transactions) == [-0.82, 407.90]
    assert payload.balance == 8200.00


def test_windows_encoded_file_is_read():
    text = "Fecha;Descripción;Valor;Saldo\n10/11/2026;PAGO NÓMINA;-1.800,00;5.000,00\n"
    _, payload = _sync(text.encode("cp1252"))
    assert payload.transactions[0].description == "PAGO NÓMINA"
    assert payload.transactions[0].amount == -1800.00


def test_bank_preamble_lines_above_the_header_are_skipped():
    text = (
        "BANCO EJEMPLO S.A.\n"
        "EXTRACTO CUENTA DE AHORROS No. 0045-0004589-3\n"
        "PERIODO: 11/11/2025 A 10/11/2026\n"
        "SALDO FINAL: $ 7.900\n"
        "\n"
        "FECHA;DESCRIPCIÓN;REFERENCIA;VALOR;SALDO\n"
        "10/11/2026;PAGO ARRIENDO BODEGA;216777;-$ 1.100;$ 7.900\n"
        "09/11/2026;ABONO VENTAS DATAFONO;628186;$ 272,56;$ 9.000\n"
    )
    connector, payload = _sync(text.encode("cp1252"))
    assert sorted(t.amount for t in payload.transactions) == [-1100.0, 272.56]
    assert payload.balance == 7900.0
    assert connector.skipped_rows == 0


def test_spanish_month_names():
    dates = parse_dates(pd.Series(["11-ene-2026", "5-abr-2026", "20-ago-2026", "24-dic-2025", "3-sept-2026"]))
    assert list(dates.dt.date) == [
        date(2026, 1, 11),
        date(2026, 4, 5),
        date(2026, 8, 20),
        date(2025, 12, 24),
        date(2026, 9, 3),
    ]


def test_other_common_header_names():
    text = (
        "Fecha Movimiento;Detalle;Monto;Saldo Disponible\n"
        "2026-08-27;TRANSF RECIBIDA;1.437,88;1.857,88\n"
        "2026-08-28;TRANSF A CTA 4589;-1.857,88;0,00\n"
    )
    _, payload = _sync(text, name="cuenta_vieja.csv")
    assert sorted(t.amount for t in payload.transactions) == [-1857.88, 1437.88]
    assert payload.balance == 0.0


def test_comma_file_keeps_reading_us_numbers_as_before():
    text = (
        "Date,Description,Amount,Balance\n2026-11-02,CARD SALES,1500,9000\n2026-11-03,COFFEE,-12.5,8987.5\n"
    )
    _, payload = _sync(text)
    assert sorted(t.amount for t in payload.transactions) == [-12.5, 1500.0]
    assert payload.balance == 8987.5
