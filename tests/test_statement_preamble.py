"""What the first demo practice run found (2026-11-17, an AI-made business, DECISIONS #61): many bank
exports put the balance and what kind of account it is in the lines above the table, not in a column.

A credit card export like "BANCO X - TARJETA DE CRÉDITO … Saldo actual: 699.69" over Fecha / Descripción
/ Monto (purchases positive) was read as a bank account whose purchases were money coming in, and the
upload stopped because it had no Balance column. The files here are made up for the test."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from aheadly.data.connectors.csv_connector import CsvConnector, describe_statement
from tests.test_example_business import _core

PROFILE = {"name": "Test", "owner_name": "", "city": ""}


def _card_xlsx(title="BANCO EJEMPLO - TARJETA DE CRÉDITO EMPRESARIAL", label="Saldo actual:", owed=699.69):
    rows = [
        [title, None, None, None],
        ["Tarjeta:", "4XXX-1234", "Titular:", "EMPRESA DE PRUEBA"],
        ["Límite de crédito:", 5000, label, owed],
        ["Movimientos del:", "01/09/2026", "al:", "31/10/2026"],
        [None, None, None, None],
        ["Fecha Transacción", "Fecha Proceso", "Descripción", "Monto"],
    ]
    day = date(2026, 10, 31)
    for n in range(40):  # purchases (positive), and a payment (negative) every 20 lines
        when = (pd.Timestamp(day) - pd.Timedelta(days=n)).strftime("%d/%m/%Y")
        payment = n % 20 == 5
        rows.append(
            [
                when,
                when,
                "PAGO RECIBIDO - GRACIAS" if payment else "GASOLINERA CENTRAL",
                -900.0 if payment else 40.0 + n,
            ]
        )
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, header=False, index=False)
    return buffer.getvalue()


def _bank_csv(balance_line="Saldo actual:,1234.50", column=False):
    head = ['"BANCO EJEMPLO"', "Consulta de Movimientos - Cuenta Corriente", balance_line, ""]
    titles = "Fecha,Descripción,Débito,Crédito" + (",Saldo" if column else "")
    lines, running = [], 1234.50
    for n in range(30):
        when = (pd.Timestamp(date(2026, 10, 31)) - pd.Timedelta(days=n)).strftime("%d/%m/%Y")
        lines.append(f"{when},VENTA TARJETA,,100.00" + (f",{running:.2f}" if column else ""))
        running -= 100
    return "\n".join(head + [titles] + lines).encode("utf-8")


def test_a_card_is_known_from_its_title_lines():
    payload = CsvConnector(_card_xlsx(), None, "tc_4417.xlsx", business_profile=PROFILE).sync()
    assert payload.account_kind == "card"
    assert payload.balance == pytest.approx(-699.69)  # what's owed, stored negative like other cards
    by_text = {}
    for t in payload.transactions:
        by_text.setdefault(t.description, set()).add(t.amount < 0)
    assert by_text["GASOLINERA CENTRAL"] == {True}  # a purchase is money going out
    assert by_text["PAGO RECIBIDO - GRACIAS"] == {False}  # paying the card brings the debt down


@pytest.mark.parametrize(
    "title, label",
    [
        ("EXAMPLE BANK - BUSINESS CREDIT CARD STATEMENT", "Current balance:"),
        ("BANCO EJEMPLO - VISA EMPRESARIAL", "Saldo a pagar:"),  # no "credit card", but a credit limit
    ],
)
def test_other_wordings_of_a_card(title, label):
    payload = CsvConnector(
        _card_xlsx(title, label, 250.0), None, "card.xlsx", business_profile=PROFILE
    ).sync()
    assert payload.account_kind == "card" and payload.balance == pytest.approx(-250.0)


def test_a_bank_balance_above_the_table():
    payload = CsvConnector(_bank_csv(), None, "cuenta.csv", business_profile=PROFILE).sync()
    assert payload.account_kind == "bank" and payload.balance == pytest.approx(1234.50)
    assert all(t.amount > 0 for t in payload.transactions)  # a bank's money in stays money in


def test_the_balance_column_wins_over_the_title_lines():
    payload = CsvConnector(
        _bank_csv("Saldo actual:,9999.00", column=True), None, "cuenta.csv", business_profile=PROFILE
    ).sync()
    assert payload.balance == pytest.approx(1234.50)


def test_an_available_balance_is_never_a_cards_debt():
    """On a card, "Saldo disponible" is the credit left, not what's owed."""
    content = _card_xlsx(label="Saldo disponible:", owed=4300.31)
    assert describe_statement(content, "card.xlsx") == {"card": True, "balance_found": False}


def test_without_any_balance_the_owner_is_asked_for_each_file():
    """Several statements, one without a balance anywhere: the page asks for that one's balance in
    its own box (what's owed, for a card) instead of refusing the whole upload."""
    no_balance = _bank_csv(balance_line="Cuenta:,03-72")
    core = _core()
    files = [("cuenta.csv", no_balance), ("tc.xlsx", _card_xlsx())]
    assert core.balances_needed(files) == [{"name": "cuenta.csv", "card": False}]
    core.connect_statements(files, {"cuenta.csv": 1234.50}, {**PROFILE, "low_cash_line": 1000})
    kinds = sorted((a["kind"], round(a["balance"], 2)) for a in core.status().accounts)
    assert kinds == [("bank", 1234.50), ("card", -699.69)]


def test_a_typed_card_balance_is_what_is_owed():
    core = _core()
    content = _card_xlsx(label="Cuenta:", owed="X")
    assert core.balances_needed([("tc.xlsx", content)]) == [{"name": "tc.xlsx", "card": True}]
    core.connect_statements([("tc.xlsx", content)], {"tc.xlsx": 320.0}, {**PROFILE, "low_cash_line": 0})
    assert core.status().accounts[0]["balance"] == pytest.approx(-320.0)
