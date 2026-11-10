import pytest

from aheadly.data.connectors.base import ConnectorNotConfigured
from aheadly.data.connectors.csv_connector import CsvConnector
from tests.conftest import TODAY
from aheadly.data.connectors.plaid_connector import PlaidConnector, plaid_to_transaction


def test_plaid_sign_convention_is_flipped():
    outflow = plaid_to_transaction(
        {"date": "2026-11-01", "amount": 25.5, "name": "Flour", "transaction_id": "a"}
    )
    inflow = plaid_to_transaction(
        {"date": "2026-11-01", "amount": -100, "name": "Sale", "transaction_id": "b"}
    )
    assert outflow.amount == -25.5 and inflow.amount == 100


def test_plaid_without_keys_reports_not_configured():
    with pytest.raises(ConnectorNotConfigured):
        PlaidConnector(client_id="", secret="").sync()


def test_csv_connector_validates_columns_and_parses_rows():
    payload = CsvConnector(
        "date,description,amount\n2026-11-01,Sales,120.5\n2026-11-02,Flour,-40", 500
    ).sync()
    assert [t.amount for t in payload.transactions] == [120.5, -40.0] and payload.balance == 500
    with pytest.raises(ValueError):
        CsvConnector("date,amount\n2026-11-01,1", 0).sync()


def test_bank_export_with_debit_credit_columns_and_spanish_headers():
    text = (
        "Fecha,Descripción,Débito,Crédito,Saldo\n2026-11-03,Ventas,,500,8700\n2026-11-02,Harina,300,,8200\n"
    )
    payload = CsvConnector(text, 8700, "extracto.csv").sync()
    assert [t.amount for t in payload.transactions] == [500.0, -300.0]
    assert payload.transactions[1].description == "Harina"


def test_sample_bank_export_files_import(tmp_path):
    from scripts.make_sample_export import bank_export

    frame = bank_export(TODAY)
    assert frame["Balance"].iloc[0] == 8200  # newest row first, ends at today's balance
    xlsx = tmp_path / "export.xlsx"
    frame.to_excel(xlsx, index=False)
    payload = CsvConnector(xlsx.read_bytes(), 8200, xlsx.name).sync()
    assert len(payload.transactions) == len(frame)
    assert sum(t.amount for t in payload.transactions) == pytest.approx(
        frame["Credit"].sum() - frame["Debit"].sum()
    )


def test_imported_bank_export_forecasts_from_full_history(core):
    """No scheduled items after a file import, so payroll and rent must stay in the learning history."""
    from scripts.make_sample_export import bank_export

    frame = bank_export(TODAY)
    core.connect(CsvConnector(frame.to_csv(index=False), 8200, "export.csv"))
    forecast = core.get_dashboard().forecast
    end_balance = forecast.points[-1].balance_p50
    assert (
        8200 - 8 * 1500 < end_balance < 8200 + 8 * 800
    ), end_balance  # ordinary weeks net a few hundred dollars
