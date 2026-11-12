"""Roadmap 2.2: every bank line gets a category; the owner's answer always wins."""

from __future__ import annotations

from datetime import timedelta

import pytest

from aheadly.ai.categorizer import (
    CATEGORIES,
    Line,
    PayeeRule,
    by_keywords,
    categorize,
    category_from_answer,
)
from aheadly.ai.scenarios import Adjustment, apply_adjustments
from aheadly.data.connectors.csv_connector import CsvConnector

from .conftest import TODAY


# ------------------------------------------------------------- keyword rules
@pytest.mark.parametrize(
    "description, amount, category",
    [
        ("ABONO VENTAS DATAFONO", 469.66, "sales"),
        ("TRANSF RECIBIDA CAFE EL TINTO FELIZ", 354.39, "sales"),
        ("CONSIGNACION EFECTIVO", 900.0, "sales"),
        ("ABONO INTERESES AHORROS", 3.5, "other_income"),
        ("PAGO NOMINA", -1330.0, "payroll"),
        ("PAGO PILA APORTES SEGURIDAD SOCIAL", -885.56, "payroll"),
        ("PAGO ARRIENDO LOCAL", -900.0, "rent"),
        ("PAGO ENEL", -210.56, "utilities"),
        ("PAGO AIR-E", -240.04, "utilities"),
        ("PAGO CLARO HOGAR", -41.9, "utilities"),
        ("PAGO DIAN RETENCION EN LA FUENTE", -176.78, "taxes"),
        ("PAGO CREDITO ROTATIVO", -5000.0, "loan"),
        ("GMF 4X1000", -2.1, "bank_fees"),
        ("CUOTA MANEJO TARJETA DEBITO", -4.62, "bank_fees"),
        ("PAGO TARJETA CREDITO VISA 9031", -812.37, "card_payment"),
        ("PAGO PSE MOLINOS EL TRIGAL", -480.0, "suppliers"),  # a PSE payment to a company
        ("COMPRA MERCADOLIBRE", -221.64, "suppliers"),
        ("COMPRA ALKOSTO BATIDORA INDUSTRIAL", -640.0, "equipment"),
        ("PAGO PSE LOGGRO POS SAS", -34.9, "other"),  # software, even though it's paid by PSE
        ("COMPRA TERPEL", -24.66, "other"),
        ("TRANSF 0045 REF 88213", -310.0, "other"),  # nothing to go on: the owner is asked (2.7)
        ("Payroll ADP", -2500.0, "payroll"),
        ("Rent - Main St", -1800.0, "rent"),
        ("IRS EFTPS", -900.0, "taxes"),
    ],
)
def test_bank_wording(description, amount, category):
    assert by_keywords(description, amount) == category


def test_words_match_whole_words_only():
    assert by_keywords("COMPRA RENTERIA", -10.0) == "other"  # 'rent' inside a word
    assert by_keywords("PAGO TAXIS LIBRES", -10.0) == "other"  # 'tax' inside a word


def test_the_same_word_reads_by_direction():
    assert by_keywords("REEMBOLSO PROVEEDOR", 50.0) == "other_income"
    assert by_keywords("PAGO PROVEEDOR", -50.0) == "suppliers"


# ------------------------------------------------------------- order of the rules
def _line(description="PAGO NOMINA", amount=-100.0, category="other", source="bank", internal=False):
    return Line(1, description, amount, category, source, internal)


def test_the_owners_answer_wins_over_everything():
    rules = [PayeeRule("pago nomina", "owner_pay")]
    assert categorize(_line(), rules) == ("owner_pay", "owner")
    assert categorize(_line(internal=True), rules) == ("owner_pay", "owner")


def test_moves_between_own_accounts():
    assert categorize(_line("TRANSF A CTA CORRIENTE 5510", internal=True), []) == (
        "transfer_internal",
        "rule",
    )
    card = _line("PAGO TARJETA CREDITO", category="card_payment", source="rule", internal=True)
    assert categorize(card, []) == ("card_payment", "rule")


def test_a_category_from_the_file_is_kept():
    assert categorize(_line("Walk-in sales", 300.0, "sales"), []) == ("sales", "bank")
    assert categorize(_line("Something", -10.0, "other"), []) == ("other", "rule")


def test_keywords_run_again_on_lines_they_placed():
    assert categorize(_line(category="other", source="rule"), []) == ("payroll", "rule")


# ------------------------------------------------------------- answers in the owner's words
@pytest.mark.parametrize(
    "answer, category",
    [
        ("loan repayment (equipment loan)", "loan"),
        ("leasing of the delivery truck", "loan"),
        ("the building's monthly administration fee", "rent"),
        ("money from my old account at the other bank", "transfer_internal"),
        ("that's my pay", "owner_pay"),
        ("my accountant's monthly fee", "other"),
    ],
)
def test_answers_in_the_owners_words(answer, category):
    assert category_from_answer(answer) == category


# ------------------------------------------------------------- through App Core
STATEMENT = "Date,Description,Amount,Balance\n" + "".join(
    f"2026-10-{d:02d},{desc},{amount},{1000 + d * 10}\n"
    for d, desc, amount in [
        (1, "ABONO VENTAS DATAFONO", 500),
        (2, "PAGO NOMINA", -400),
        (3, "TRANSF 0045 REF 88213", -310),
        (5, "PAGO ENEL", -50),
        (8, "ABONO VENTAS DATAFONO", 500),
        (9, "TRANSF 0045 REF 88213", -310),
        (12, "ABONO VENTAS DATAFONO", 500),
        (15, "ABONO VENTAS DATAFONO", 500),
        (20, "TRANSF INTERBANCARIA RECIBIDA 1180", 250),
        (22, "ABONO VENTAS DATAFONO", 500),
        (29, "ABONO VENTAS DATAFONO", 500),
    ]
)
PROFILE = {"name": "Test", "owner_name": "", "city": ""}


@pytest.fixture
def uploaded(core):
    core.connect(CsvConnector(STATEMENT, None, "cuenta.csv", business_profile=PROFILE))
    return core


def _categories(core):
    return {
        r["description"]: r["category"]
        for r in core.repo._conn.execute("SELECT description, category FROM transactions")
    }


def test_upload_puts_lines_in_categories(uploaded):
    found = _categories(uploaded)
    assert (found["ABONO VENTAS DATAFONO"], found["PAGO NOMINA"], found["PAGO ENEL"]) == (
        "sales",
        "payroll",
        "utilities",
    )
    assert found["TRANSF 0045 REF 88213"] == "other"


def test_an_answer_changes_every_matching_line(uploaded):
    assert uploaded.answer_payee("TRANSF 0045 REF 88213", "loan for the oven") == "loan"
    assert _categories(uploaded)["TRANSF 0045 REF 88213"] == "loan"
    assert uploaded.monthly_category_totals()["2026-10"]["loan"] == -620.0


def test_an_answer_applies_to_later_uploads(uploaded):
    uploaded.set_payee_rule("TRANSF 0045 REF 88213", "loan")
    later = "Date,Description,Amount,Balance\n2026-11-03,TRANSF 0045 REF 88213,-310,2000\n"
    uploaded.connect(CsvConnector(later, None, "noviembre.csv", business_profile=PROFILE))
    rows = uploaded.repo._conn.execute(
        "SELECT category, category_source FROM transactions WHERE date='2026-11-03'"
    ).fetchall()
    assert [tuple(r) for r in rows] == [("loan", "owner")]


def test_money_from_the_owners_own_account_is_not_income(uploaded):
    before = uploaded.repo.flow_totals(uploaded.status().business.id, TODAY.replace(month=1, day=1))
    assert uploaded.answer_payee("TRANSF INTERBANCARIA RECIBIDA 1180", "money from my old account") == (
        "transfer_internal"
    )
    after = uploaded.repo.flow_totals(uploaded.status().business.id, TODAY.replace(month=1, day=1))
    assert after["money_in"] == before["money_in"] - 250


def test_an_unknown_category_is_refused(uploaded):
    with pytest.raises(ValueError):
        uploaded.set_payee_rule("PAGO ENEL", "snacks")
    with pytest.raises(ValueError):
        uploaded.set_payee_rule("   ", "rent")
    assert "snacks" not in CATEGORIES


# ------------------------------------------------------------- the What-if 'change sales' fix
def test_a_sales_change_is_a_percent_of_the_real_weekly_sales():
    change = Adjustment("revenue_change", {"percent": 10})
    items = apply_adjustments([], [change], TODAY, 56, weekly_sales=2000.0)
    assert [(i.amount, i.recurrence) for i in items] == [(200.0, "weekly")]
    with pytest.raises(ValueError):
        apply_adjustments([], [change], TODAY, 56, weekly_sales=0.0)


def test_weekly_sales_come_from_the_statement(core):
    days = [TODAY - timedelta(days=n) for n in range(56, 0, -1)]
    statement = "Date,Description,Amount,Balance\n" + "".join(
        f"{d.isoformat()},ABONO VENTAS DATAFONO,700,{1000 + 700 * i}\n" for i, d in enumerate(days)
    )
    core.connect(CsvConnector(statement, None, "cuenta.csv", business_profile=PROFILE))
    assert core.weekly_sales() == pytest.approx(4900.0)
