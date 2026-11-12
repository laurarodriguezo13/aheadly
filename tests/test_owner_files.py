"""Roadmap 2.5: files the owner keeps, in any layout: read, previewed, used only when confirmed."""

from __future__ import annotations

import json
from datetime import date

import pytest

from aheadly.ai.llm_client import LLMError, LLMReply, ToolCall
from aheadly.data.connectors.owner_files import read_owner_file

from .test_businesses import BUSINESSES, import_business
from .test_example_business import _core

TODAY = date(2026, 11, 11)


def _read(text: str, name: str = "file.csv", kind: str | None = None):
    return read_owner_file(text.encode("utf-8"), name, TODAY, kind)


# ------------------------------------------------------------- what kind of file
@pytest.mark.parametrize(
    "header, kind",
    [
        ("Date,Description,Amount", "upcoming_payments"),
        ("Fecha;Concepto;Tipo;Valor", "upcoming_payments"),
        ("Cliente,Factura,Vence,Saldo", "receivables"),
        ("No. Siniestro,Fecha pago esperada,Valor", "receivables"),
        ("Name,Position,Weekly pay", "employees"),
        ("Fecha,Cuenta,Descripción,Valor", "ledger"),
        ("Artículo,Cantidad,Costo unitario", "inventory"),
    ],
)
def test_the_column_titles_say_what_it_is(header, kind):
    sep = ";" if ";" in header else ","
    row = sep.join("1" for _ in header.split(sep))
    assert _read(f"{header}\n{row}\n").kind == kind


def test_titles_above_the_header_are_skipped():
    read = _read("Mis próximos pagos\n\nFecha,Concepto,Valor\n2026-12-01,Arriendo bodega,900\n")
    assert (read.kind, read.rows, read.total) == ("upcoming_payments", 1, -900.0)


def test_a_file_we_cant_place_asks_the_owner():
    read = _read("Color,Size\nred,big\n")
    assert read.kind is None and read.problem
    forced = _read("Color,Size\nred,big\n", kind="inventory")
    assert forced.problem == "Which column has the item, quantity, unit cost? Pick it below."
    assert forced.details["missing_roles"] == ["item", "quantity", "unit_cost"]


# ------------------------------------------------------------- upcoming payments
def test_minus_for_money_out_when_the_file_uses_both_signs():
    read = _read("Date,Description,Amount\n2026-11-14,New oven,-7500\n2026-12-16,Christmas order,5500\n")
    assert [(i.label, i.amount) for i in read.items] == [("New oven", -7500.0), ("Christmas order", 5500.0)]


def test_a_list_of_positive_amounts_is_a_list_of_payments():
    read = _read("Date,Item,Amount\n2026-12-02,New laptop,1650.00\n2026-12-09,Hosting,214.50\n")
    assert [i.amount for i in read.items] == [-1650.0, -214.5]
    assert read.items[0].label == "New laptop"


def test_a_type_column_says_in_or_out():
    read = _read(
        "Fecha;Concepto;Tipo;Valor\n14/11/2026;Horno;Egreso;7.500\n16/12/2026;Pedido café;Ingreso;5.500\n"
    )
    assert [(i.amount, i.due_date) for i in read.items] == [
        (-7500.0, date(2026, 11, 14)),
        (5500.0, date(2026, 12, 16)),
    ]


def test_past_rows_are_counted_but_not_planned():
    read = _read("Date,Description,Amount\n2026-10-01,Old bill,-100\n2026-12-01,New bill,-200\n")
    assert (read.rows, len(read.items), read.details["already_past"]) == (2, 1, 1)


# ------------------------------------------------------------- receivables
def test_overdue_invoices_are_a_maybe_and_very_old_ones_are_not_counted():
    read = _read(
        "Cliente,Factura,Vence,Saldo\n"
        "Constructora,FV-1,2026-11-20,1000\n"
        "Colegio,FV-2,2026-10-12,240\n"  # 30 days late
        "Restaurante,FV-3,2026-09-03,186.50\n"  # 69 days late
    )
    assert (read.rows, read.total, read.overdue_rows) == (3, 1426.5, 2)
    labels = {i.label: i for i in read.items}
    assert labels["Constructora – FV-1"].due_date == date(2026, 11, 20)
    late = labels["Colegio – FV-2 (overdue)"]
    assert (late.certainty, late.due_date, late.amount) == ("maybe", date(2026, 11, 25), 240.0)
    assert [d["label"] for d in read.details["doubtful"]] == ["Restaurante – FV-3"]


# ------------------------------------------------------------- summaries only
def test_employees_add_nothing_and_are_compared_with_the_payroll_found():
    core = _core()
    core.load_example()
    path = BUSINESSES / "panaderia-la-esquina/files/empleados.xlsx"
    read = core.read_owner_file(path.read_bytes(), path.name)
    assert (read.kind, read.total, read.details["period"], read.items) == ("employees", 1331.2, "weekly", [])
    assert read.details["payroll_found_per_month"] == pytest.approx(read.details["per_month"], rel=0.01)


def test_inventory_lists_what_is_running_low():
    read = _read(
        "Artículo,Cantidad,Nivel de reorden,Costo unitario\nCemento,140,80,7.90\nTubo PVC,65,80,3.10\n"
    )
    assert (read.total, read.details["below_reorder"], read.items) == (140 * 7.9 + 65 * 3.1, ["Tubo PVC"], [])


# ------------------------------------------------------------- using a file
def test_nothing_is_used_before_the_owner_confirms_and_nothing_twice():
    core = _core()
    core.load_example()  # the example already plans the bakery's upcoming payments
    before = len(core.planned_items())
    path = BUSINESSES / "panaderia-la-esquina/files/proximos_pagos.xlsx"
    read = core.read_owner_file(path.read_bytes(), path.name)
    assert len(core.planned_items()) == before
    assert read.details["already_planned"] == 5
    assert core.use_owner_file(read) == 0
    assert len(core.planned_items()) == before
    assert core.uploaded_files()[0]["kind"] == "upcoming_payments"


def test_a_claims_file_replaces_the_insurer_payments_found_in_the_statement():
    core = import_business("taller-los-pistones")
    path = BUSINESSES / "taller-los-pistones/files/reclamaciones_pendientes.xlsx"
    core.use_owner_file(core.read_owner_file(path.read_bytes(), path.name))
    money_in = [label for _, amount, label in core._events(date(2027, 1, 5)) if amount > 0]
    assert money_in == [
        "SIN-26400",
        "SIN-26407",
        "SIN-26414",
        "SIN-26421",
    ]  # each claim once, no insurer guess


def test_a_file_with_a_problem_is_refused():
    core = _core()
    core.load_example()
    with pytest.raises(ValueError):
        core.use_owner_file(core.read_owner_file(b"Color,Size\nred,big\n", "colors.csv"))


# ------------------------------------------------------------- the assistant only sees column titles
class _FakeModel:
    name = "fake"

    def __init__(self, kind="inventory", fail=False):
        self.kind, self.fail, self.seen = kind, fail, []

    def chat(self, messages, tools=None):
        self.seen.append(json.dumps(messages, ensure_ascii=False))
        if self.fail:
            raise LLMError("quota")
        columns = {
            "item": "Referencia interna",
            "quantity": "Unds",
            "unit_cost": "Precio compra",
            "date": "Nope",
        }
        return LLMReply(
            tool_calls=[ToolCall("1", "classify_owner_file", {"kind": self.kind, "columns": columns})]
        )


def _with(model):
    core = _core()
    core.load_example()
    core.translator._llm = model
    return core


ODD = "Referencia interna,Unds,Precio compra\nANA PRUEBA RUIZ,12,268\n".encode()


def test_when_titles_dont_say_the_assistant_suggests_seeing_titles_only():
    model = _FakeModel("inventory")
    read = _with(model).read_owner_file(ODD, "cosas.csv")
    assert read.details["kind_from"] == "ai" and read.kind == "inventory"
    assert (read.problem, read.rows, read.total) == (None, 1, 12 * 268)  # "Nope" isn't a title: ignored
    sent = " ".join(model.seen)
    assert "Referencia interna" in sent and "ANA PRUEBA RUIZ" not in sent and "268" not in sent


def test_an_invalid_or_failed_suggestion_leaves_it_to_the_owner():
    for model in (_FakeModel("spaceship"), _FakeModel(fail=True)):
        read = _with(model).read_owner_file(ODD, "cosas.csv")
        assert read.kind is None and read.problem


def test_an_employee_list_never_reaches_the_assistant():
    model = _FakeModel()
    path = BUSINESSES / "panaderia-la-esquina/files/empleados.xlsx"
    _with(model).read_owner_file(path.read_bytes(), path.name)
    assert model.seen == []  # the titles were clear: the model was never asked


# ------------------------------------------------------------- files unlike the test businesses' ones
def test_total_rows_are_left_out():
    read = _read("Nombre,Cargo,Salario mensual\nAna,Cajera,800\nLuis,Panadero,900\nTOTAL,,1700\n")
    assert (read.rows, read.total, read.details["total_rows"]) == (2, 1700.0, 1)


def test_the_data_can_be_on_any_sheet():
    import io

    import pandas as pd

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        pd.DataFrame({"Notas": ["Cartera 2026"]}).to_excel(writer, sheet_name="Portada", index=False)
        pd.DataFrame({"Cliente": ["A"], "Factura": ["F1"], "Vence": ["2026-11-30"], "Saldo": [500]}).to_excel(
            writer, sheet_name="Cartera", index=False
        )
    read = read_owner_file(buffer.getvalue(), "cartera.xlsx", TODAY)
    assert (read.kind, read.total) == ("receivables", 500.0)


def test_titles_the_app_doesnt_know_are_pointed_at_by_the_owner():
    text = "Cte.,No. Fact.,F. Vto.,Importe pdte.\nTienda A,F-1,30/11/2026,500\n"
    assert _read(text).kind is None
    asked = _read(text, kind="receivables")
    assert (
        asked.details["missing_roles"] == ["due"]
        and asked.problem == "Which column has the due date? Pick it below."
    )
    read = read_owner_file(
        text.encode(), "file.csv", TODAY, "receivables", {"due": "F. Vto.", "customer": "Cte."}
    )
    assert [(i.label, i.amount, i.due_date) for i in read.items] == [("Tienda A", 500.0, date(2026, 11, 30))]


def test_a_file_without_titles_keeps_its_first_row():
    text = "Horno,7500,14/11/2026\nHarina,4000,15/12/2026\n"
    read = _read(text)
    assert (
        read.headers == ["Column 1", "Column 2", "Column 3"]
        and read.details["samples"]["Column 1"] == "Horno"
    )
    hint = {"label": "Column 1", "amount": "Column 2", "date": "Column 3"}
    read = read_owner_file(text.encode(), "file.csv", TODAY, "upcoming_payments", hint)
    assert [i.label for i in read.items] == ["Horno", "Harina"]


def test_rows_it_cant_read_are_counted_for_the_owner():
    read = _read("Fecha,Concepto,Valor\n15 nov,Arriendo,900\nfin de mes,Nómina,5200\n")
    assert (read.rows, read.details["skipped"]) == (1, 1)


def test_a_bank_statement_in_the_wrong_place_is_pointed_out():
    read = _read(
        "Fecha,Descripción,Valor,Saldo\n01/10/2026,PAGO NOMINA,-1300,5000\n02/10/2026,ABONO VENTAS,500,5500\n"
    )
    assert read.problem.startswith("This looks like a bank statement")
