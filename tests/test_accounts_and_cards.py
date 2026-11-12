"""Roadmap 2.1: several statements, several accounts, a credit card, and transfers between the
owner's own accounts that are neither income nor spending."""

from datetime import date

import pytest

from aheadly.data.connectors.csv_connector import CsvConnector, account_label

BANK_A = (
    "Date,Description,Amount,Balance\n"
    "2026-10-01,CARD SALES,1000.00,6000.00\n"
    "2026-10-02,TRANSF A CTA AHORROS 7723,-2000.00,4000.00\n"
    "2026-10-03,PAGO TARJETA CREDITO VISA 9031,-300.00,3700.00\n"
    "2026-10-04,TRANSF A CTA AHORROS PERSONAL OWNER,-500.00,3200.00\n"
) + "".join(f"2026-10-{d:02d},CARD SALES,100.00,{3200 + 100 * (d - 4):.2f}\n" for d in range(5, 26))
SAVINGS_B = "Fecha;Descripción;Valor;Saldo\n02/10/2026;TRANSF RECIBIDA CTA CORRIENTE;2.000,00;5.000,00\n"
CARD = (
    "Date,Description,Charges,Payments,Balance owed\n"
    "09/28/2026,COMPRA TERPEL,120.00,,420.00\n"
    "10/03/2026,PAGO RECIBIDO GRACIAS,,300.00,120.00\n"
    "10/05/2026,COMPRA HOMECENTER,80.50,,200.50\n"
)


def _connectors(*files: tuple[str, str]) -> list[CsvConnector]:
    profile = {"name": "Ferretería", "owner_name": "", "city": "", "low_cash_line": 1000.0}
    return [CsvConnector(text, None, name, business_profile=profile) for name, text in files]


def _row_count(core, where: str = "1=1") -> int:
    return core.repo._conn.execute(f"SELECT COUNT(*) FROM transactions WHERE {where}").fetchone()[0]


# ------------------------------------------------------------- credit card statements
def test_a_card_statement_is_read_as_a_card_with_its_debt():
    connector = CsvConnector(CARD, None, "visa_empresarial_9031.csv")
    payload = connector.sync()
    assert payload.account_kind == "card"
    assert sorted(t.amount for t in payload.transactions) == [-120.0, -80.5, 300.0]
    assert payload.balance == -200.50  # money owed on the card
    assert connector.balance_breaks == 0


def test_a_spanish_card_statement():
    text = "Fecha;Descripción;Cargos;Pagos;Saldo adeudado\n05/10/2026;COMPRA EXITO;45,00;;245,00\n"
    payload = CsvConnector(text, None, "tarjeta.csv").sync()
    assert (payload.account_kind, payload.transactions[0].amount, payload.balance) == ("card", -45.0, -245.0)


def test_a_bank_statement_is_a_bank_account_named_after_its_file():
    payload = CsvConnector(BANK_A, None, "cuenta_corriente_5510.csv").sync()
    assert (payload.account_kind, payload.account_name) == ("bank", "Cuenta corriente 5510")


@pytest.mark.parametrize(
    "filename, name",
    [
        ("extracto_ahorros_4471_2026-05_2026-11.csv", "Ahorros 4471"),
        ("statement_checking_1234_20261110.csv", "Checking 1234"),
        ("visa_empresarial_9031.xlsx", "Visa empresarial 9031"),
        ("Movimientos 10-11-2026.csv", "Movimientos 10-11-2026"),  # nothing else left: keep it all
        ("2026-11.csv", "2026-11"),
    ],
)
def test_account_names_leave_out_dates_and_export_words(filename, name):
    assert account_label(filename) == name


# ------------------------------------------------------------- several statements of one account
@pytest.mark.parametrize("order", ["oldest file first", "newest file first"])
def test_two_overlapping_statements_of_one_account_are_one_account(core, order):
    older = "Date,Description,Amount,Balance\n" + "".join(
        f"2026-09-{d:02d},CARD SALES,100.00,{1000 + 100 * d:.2f}\n" for d in range(1, 21)
    )
    newer = "Date,Description,Amount,Balance\n" + "".join(
        f"2026-09-{d:02d},CARD SALES,100.00,{1000 + 100 * d:.2f}\n" for d in range(15, 31)
    )
    files = [("extracto_sep_a.csv", older), ("extracto_sep_b.csv", newer)]
    core.connect_files(_connectors(*(files if order == "oldest file first" else files[::-1])))
    business_id = core.status().business.id
    assert len(core.repo.list_accounts(business_id)) == 1
    assert core.repo.current_balance(business_id) == 4000.0  # the newest file's closing balance
    assert _row_count(core) == 30  # 20 + 16 lines, 6 shared


# ------------------------------------------------------------- several accounts and a card
def test_bank_savings_and_card_together(core):
    core.connect_files(
        _connectors(
            ("cuenta_corriente_5510.csv", BANK_A),
            ("cuenta_ahorros_7723.csv", SAVINGS_B),
            ("visa_empresarial_9031.csv", CARD),
        )
    )
    business_id = core.status().business.id
    accounts = {a["name"]: a for a in core.repo.list_accounts(business_id)}
    assert len(accounts) == 3 and accounts["Visa empresarial 9031"]["kind"] == "card"
    assert core.repo.current_balance(business_id) == pytest.approx(5300.0 + 5000.0)  # card debt isn't cash

    # checking → savings: both sides are a transfer, not income or spending
    transfer = "is_internal_transfer=1 AND COALESCE(category, '') != 'card_payment'"
    assert _row_count(core, transfer) == 2
    # paying the card from checking: both sides flagged, the purchases stay as spending
    assert _row_count(core, "category='card_payment' AND is_internal_transfer=1") == 2
    assert _row_count(core, "is_internal_transfer=0 AND description LIKE 'COMPRA%'") == 2
    # the owner's pay goes to an account we don't have: it's real money out
    assert _row_count(core, "is_internal_transfer=0 AND description LIKE '%PERSONAL OWNER%'") == 1
    assert core.internal_transfer_counts() == {"transfers": 1, "card_payments": 1}


def test_transfers_dont_count_as_money_in_or_out(core):
    core.connect_files(
        _connectors(("cuenta_corriente_5510.csv", BANK_A), ("cuenta_ahorros_7723.csv", SAVINGS_B))
    )
    business_id = core.status().business.id
    totals = core.repo.flow_totals(business_id, date(2026, 9, 1))
    assert totals["money_out"] == pytest.approx(300.0 + 500.0)  # card payment and owner pay, not the $2,000
    flows = core.repo.daily_net_flow(business_id).set_index("date")["net_flow"]
    assert flows.loc["2026-10-02"] == 0.0  # the transfer day nets out


def test_one_file_still_works_as_before(core):
    core.connect_files(_connectors(("cuenta_corriente_5510.csv", BANK_A)))
    assert core.repo.current_balance(core.status().business.id) == 5300.0
