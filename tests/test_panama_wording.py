"""What the first demo practice run found in the statement's wording (2026-11-17, an AI-made business
in Panama, DECISIONS #62). The keyword rules were written from six Colombian test businesses; Panama
and the rest of Central America say "planilla" for payroll and pay taxes to the DGI. The owner's pay
went to "ACH ENVIADO <bank> <the owner's name>", not to a savings account, so it was asked as a
mystery payment. A monthly budget with the months as columns was asked which column is the date.
The files here are made up for the test."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import pytest

from aheadly.ai.categorizer import by_keywords
from aheadly.core import onboarding
from aheadly.data.connectors.csv_connector import CsvConnector, preamble, statement_holder
from aheadly.data.connectors.owner_files import read_owner_file


@pytest.mark.parametrize(
    "line, category",
    [
        ("PAGO DE PLANILLA BGNET LOTE 26111", "payroll"),
        ("PAGO CSS SIPE PLANILLA 10/2026", "payroll"),
        ("PAGO DGI ETAX2 ITBMS 10/2026", "taxes"),
        ("PAGO DGI ETAX2 ISR ESTIMADA 2-2026", "taxes"),
        ("PAGO MUNICIPIO DE PANAMA RUC 155", "taxes"),
        ("PAGO DE SERVICIO ENSA NIS 4411", "utilities"),
        ("PAGO DE SERVICIO NATURGY NIS 9", "utilities"),
        ("PAGO IDAAN CTA 3321", "utilities"),
        ("PAGO DE SERVICIO +MOVIL CTA 66", "utilities"),
        ("PAGO CABLE ONDA 1234", "utilities"),
    ],
)
def test_central_american_bank_wording(line, category):
    assert by_keywords(line, -100.0) == category


def _statement(holder_label="Titular:", holder="SERV DE CLIMA EJEMPLO GONZALEZ S A"):
    head = ['"BANCO EJEMPLO"', f"{holder_label},{holder}", "Saldo actual:,5000.00", ""]
    rows = ["Fecha,Descripción,Débito,Crédito"]
    for n in range(60):
        when = (pd.Timestamp(date(2026, 10, 31)) - pd.Timedelta(days=n)).strftime("%d/%m/%Y")
        rows.append(f"{when},VENTA COMERCIO,,300.00")
        if n % 14 == 0:
            rows.append(f"{when},ACH ENVIADO BANCO DOS PEDRO GONZALEZ,900.00,")
            rows.append(f"{when},ACH ENVIADO BANCO DOS MARTA RUIZ,250.00,")
    return "\n".join(head + rows).encode("utf-8")


def test_the_holder_is_read_from_the_title_lines():
    assert statement_holder(preamble(_statement(), "x.csv")) == "SERV DE CLIMA EJEMPLO GONZALEZ S A"
    assert statement_holder(preamble(_statement("Account holder:", "ACME LTD"), "x.csv")) == "ACME LTD"
    assert CsvConnector(_statement(), None, "x.csv").sync().holder == "SERV DE CLIMA EJEMPLO GONZALEZ S A"


def test_a_transfer_to_someone_with_the_business_surname_may_be_the_owner():
    """Only a question ("Is … your own pay?"); the owner says yes or no."""
    names = onboarding.owner_name_words("SERV DE CLIMA EJEMPLO GONZALEZ S A", "")
    assert "gonzalez" in names and "serv" not in names
    assert onboarding.may_be_owner_pay("ACH ENVIADO BANCO DOS PEDRO GONZALEZ", names)
    assert not onboarding.may_be_owner_pay("ACH ENVIADO BANCO DOS MARTA RUIZ", names)
    assert onboarding.may_be_owner_pay("TRANSF A CTA AHORROS M GOMEZ", set())  # as before
    assert not onboarding.may_be_owner_pay("GOOGLE *WORKSPACE GONZALEZ", names)  # a purchase, not a transfer


def test_the_upload_asks_about_the_owners_pay():
    from tests.test_example_business import _core

    core = _core(today=date(2026, 11, 1))
    core.connect_statements(
        [("cuenta.csv", _statement())],
        {},
        {"name": "ClimaEjemplo", "owner_name": "", "city": "", "low_cash_line": 1000},
    )
    asked = [q for q in core.onboarding()["questions"] if q.kind == "owner_pay"]
    assert [q.payee for q in asked] == ["ACH ENVIADO BANCO DOS PEDRO GONZALEZ"]


def _budget_by_month() -> bytes:
    rows = [
        ["FLUJO DE CAJA 2026 - EMPRESA EJEMPLO", None, None, None, None, None],
        ["Concepto", "Enero", "Febrero", "Marzo", "Abril", "Total"],
        ["Ventas", 10000, 11000, 9000, 12000, 42000],
        ["Planilla", -6000, -6000, -6000, -6000, -24000],
        ["Alquiler", -1500, -1500, -1500, -1500, -6000],
    ]
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, header=False, index=False)
    return buffer.getvalue()


@pytest.mark.parametrize("months", [["Enero", "Febrero", "Marzo"], ["Jan 2026", "Feb 2026", "Mar 2026"]])
def test_a_budget_with_months_as_columns_is_named_not_mapped(months):
    if months[0] == "Jan 2026":
        frame = pd.DataFrame([["Item", *months], ["Sales", 1, 2, 3]])
        buffer = BytesIO()
        frame.to_excel(buffer, header=False, index=False)
        content = buffer.getvalue()
    else:
        content = _budget_by_month()
    read = read_owner_file(content, "flujo.xlsx", date(2026, 11, 17))
    assert read.kind is None and read.details["looks_like"] == "budget_by_month"
    assert "doesn't use" in read.problem  # said in words, not "which column is the date?"
    assert "missing_roles" not in read.details


def test_a_payroll_batch_number_is_not_a_new_payee():
    """Every payroll batch had its own lot number, so each was "a payee never seen before"."""
    from aheadly.core.pattern_rules import lines_frame, unusual_charge

    rows, n = [], 0
    for month in range(5, 11):
        for day_ in (14, 28):
            n += 1
            rows.append(
                (
                    n,
                    f"2026-{month:02d}-{day_}",
                    -3200.0 - n,
                    f"PAGO DE PLANILLA LOTE 26{month:02d}{day_}",
                    "other",
                    0,
                )
            )
        for d in range(1, 28, 3):
            n += 1
            rows.append((n, f"2026-{month:02d}-{d:02d}", -40.0, "COMPRA FERRETERIA", "suppliers", 0))
    assert unusual_charge(lines_frame(rows), date(2026, 11, 1)) == []


# ------------------------------------------- the owner's spreadsheets (DECISIONS #62, same run)
def _xlsx(rows) -> bytes:
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, header=False, index=False)
    return buffer.getvalue()


TODAY = date(2026, 11, 17)


def test_receivables_count_what_is_still_owed():
    """Monto / Abonado / Saldo / Pagó el: a paid invoice is not money to come."""
    content = _xlsx(
        [
            ["CUENTAS POR COBRAR", None, None, None, None, None, None],
            ["Factura #", "Cliente", "Monto", "Abonado", "Saldo", "Vence", "Pagó el"],
            ["001", "Hotel Uno", 1850, 1850, 0, "2026-07-31", "2026-07-27"],
            ["002", "Clínica Dos", 13600, 6800, 6800, "2026-11-29", None],
            ["003", "Colegio Tres", 1200, 0, 1200, "2026-12-05", None],
            ["004", "Farmacia Cuatro", 1650, 1650, None, "2026-08-30", "2026-08-28"],
            ["TOTAL", None, 18300, 10300, 8000, None, None],
        ]
    )
    read = read_owner_file(content, "cxc.xlsx", TODAY)
    assert read.kind == "receivables"
    assert sorted((i.label, i.amount) for i in read.items) == [
        ("Clínica Dos – 002", 6800.0),
        ("Colegio Tres – 003", 1200.0),
    ]
    assert read.overdue_rows == 0 and read.total == 8000.0


def test_a_receivables_file_with_only_a_balance_column_still_reads():
    content = _xlsx([["Cliente", "Saldo", "Vence"], ["Uno", 500, "2026-12-01"], ["Dos", 300, "2026-12-10"]])
    read = read_owner_file(content, "cxc.xlsx", TODAY)
    assert read.kind == "receivables" and read.total == 800.0 and len(read.items) == 2


def test_upcoming_payments_with_what_whom_status_and_loose_dates():
    content = _xlsx(
        [
            ["PAGOS QUE VIENEN", None, None, None, None],
            ["Fecha", "Qué", "A quién", "Monto", "Estado"],
            ["2026-11-13", "Quincena 15 nov", "Planilla", 3221.41, "PAGADO"],
            ["2026-11-30", "Quincena 30 nov", "Planilla", 3200, None],
            ["~10 dic", "SALDO CONTENEDOR (70%)", "Proveedor Uno", 20300, None],
            ["aprox. 22 de diciembre", "Canastas", "Super", 400, None],
            ["ene", "Bomba de vacío nueva", "Repuestos", 450, None],
        ]
    )
    read = read_owner_file(content, "pagos.xlsx", TODAY)
    assert read.kind == "upcoming_payments" and read.details["skipped"] == 0
    found = {(i.label, i.due_date, i.amount, i.certainty) for i in read.items}
    assert found == {
        ("Planilla – Quincena 30 nov", date(2026, 11, 30), -3200.0, "confirmed"),
        ("Proveedor Uno – SALDO CONTENEDOR (70%)", date(2026, 12, 10), -20300.0, "confirmed"),
        ("Super – Canastas", date(2026, 12, 22), -400.0, "confirmed"),
        ("Repuestos – Bomba de vacío nueva", date(2027, 1, 15), -450.0, "maybe"),  # a month alone
    }


def test_a_listed_card_payment_doesnt_count_again_when_the_card_is_here():
    from tests.test_example_business import _core
    from tests.test_statement_preamble import _bank_csv, _card_xlsx

    content = _xlsx(
        [["Fecha", "Qué", "A quién", "Monto"], ["2026-12-08", "Tarjeta Visa (corte 20/nov)", "Banco", 1400],
         ["2026-12-10", "Saldo contenedor", "Proveedor", 20300]]
    )  # fmt: skip
    core = _core(today=date(2026, 11, 1))
    core.connect_statements([("cuenta.csv", _bank_csv())], {}, {"name": "X", "owner_name": "", "city": "",
                                                               "low_cash_line": 0})  # fmt: skip
    assert len(core.read_owner_file(content, "pagos.xlsx").items) == 2  # no card statement: keep it
    core = _core(today=date(2026, 11, 1))
    core.connect_statements([("cuenta.csv", _bank_csv()), ("tc.xlsx", _card_xlsx())], {},
                            {"name": "X", "owner_name": "", "city": "", "low_cash_line": 0})  # fmt: skip
    read = core.read_owner_file(content, "pagos.xlsx")
    assert [i.label for i in read.items] == ["Proveedor – Saldo contenedor"]
    assert read.details["card_payments_left_out"] == 1


def test_owner_payments_pair_by_name_first():
    """The Dec 31 income tax ($3,600) once stood in for the Dec 31 payroll ($3,221)."""
    from aheadly.ai.recurring import pair_duplicates

    events = [
        (date(2026, 12, 31), -3221.0, "Pago de planilla bgnet lote 26111", True),
        (date(2026, 12, 31), -3600.0, "DGI – ISR estimada 3ra partida", False),
        (date(2026, 12, 31), -3250.0, "Planilla – Quincena 31 dic", False),
    ]
    assert pair_duplicates(events) == {0: 2}
