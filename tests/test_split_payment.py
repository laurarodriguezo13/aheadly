"""Roadmap 3.7 (DECISIONS #63): split a big once-only payment in two, half on its date and half weeks
later. The first demo practice run's business had a $20,300 stock balance due just before its tight
weeks; moving all of it didn't help and splitting it was the real fix."""

from __future__ import annotations

from datetime import date

import pytest

from aheadly.ai import templates
from aheadly.ai.scenarios import apply_adjustments, parse_adjustment
from aheadly.core import actions
from aheadly.domain import ScheduledItem

TODAY = date(2026, 11, 17)


def test_split_item_keeps_part_and_moves_the_rest():
    items = [ScheduledItem("Container balance", -20300.0, date(2026, 12, 10), kind="bill")]
    adj = parse_adjustment({"type": "split_item", "label": "Container", "new_date": "2027-01-14"})
    out = apply_adjustments(items, [adj], TODAY)
    assert sorted((i.due_date, i.amount) for i in out) == [
        (date(2026, 12, 10), -10150.0),
        (date(2027, 1, 14), -10150.0),
    ]
    assert items[0].amount == -20300.0  # the owner's own list isn't changed by a what-if


def test_split_item_share_and_checks():
    items = [ScheduledItem("Oven", -7500.0, date(2026, 12, 1))]
    adj = parse_adjustment({"type": "split_item", "label": "Oven", "new_date": "2026-12-29", "share": 0.4})
    out = apply_adjustments(items, [adj], TODAY)
    assert sorted(i.amount for i in out) == [-4500.0, -3000.0]
    with pytest.raises(ValueError, match="new_date"):
        parse_adjustment({"type": "split_item", "label": "Oven"})
    with pytest.raises(ValueError, match="share"):
        parse_adjustment({"type": "split_item", "label": "Oven", "new_date": "2026-12-29", "share": 1.5})


def test_split_words_and_message():
    words = templates.action_words(
        "split_payment", payee="Climacentro", amount=20300, when="2026-12-10", new_when="2027-01-14"
    )
    assert words["label"] == "Pay Climacentro in two parts"
    assert "$10,150" in words["detail"] and "Dec 10" in words["detail"] and "Jan 14" in words["detail"]
    text = templates.message_text(
        {"kind": "split_payment", "payee": "Climacentro", "amount": 20300, "part": 10150,
         "date": "2026-12-10", "new_date": "2027-01-14", "business": "ClimaEjemplo", "owner": "Ana"}
    )  # fmt: skip
    assert "$10,150" in text and "Jan 14" in text and "Ana" in text


def test_the_bakery_gets_a_split_only_if_it_helps():
    """On a test business whose fix is moving the oven, splitting is tried too and kept only if it
    helps; the moved oven stays among the suggestions."""
    from tests.test_businesses import import_business

    core = import_business("panaderia-la-esquina", with_one_offs=True)
    found = core.suggested_fixes()
    kinds = [a["kind"] for a in found]
    assert "move_payment" in kinds
    for action in found:
        if action["kind"] == "split_payment":
            assert action["adjustments"][0]["type"] == "split_item"
            assert action["impact"]["lowest_after"] > action["impact"]["lowest_before"]


def test_a_split_is_a_message_kind_and_costs_nothing():
    assert "split_payment" in actions.MESSAGE_KINDS and actions.COST["split_payment"] == 0


def test_payments_from_a_file_get_a_category_from_their_name():
    """A tax from the owner's list was offered to split; taxes and payroll are never moved."""
    from io import BytesIO

    import pandas as pd

    from aheadly.data.connectors.owner_files import read_owner_file

    buffer = BytesIO()
    pd.DataFrame(
        [["Fecha", "Qué", "A quién", "Monto"], ["2026-12-31", "ISR estimada 3ra partida", "DGI", 3600],
         ["2026-12-15", "Quincena 15 dic", "Planilla", 3200], ["2026-12-10", "Saldo contenedor", "Proveedor", 20300]]
    ).to_excel(buffer, header=False, index=False)  # fmt: skip
    read = read_owner_file(buffer.getvalue(), "pagos.xlsx", TODAY)
    assert {i.label: i.category for i in read.items} == {
        "DGI – ISR estimada 3ra partida": "taxes",
        "Planilla – Quincena 15 dic": "payroll",
        "Proveedor – Saldo contenedor": "suppliers",  # can be moved or split
    }


def test_a_no_to_moving_a_payment_is_a_no_to_splitting_it():
    from aheadly.core.actions import ruled_out

    rules = [{"kind": "move_payment", "label": "New oven"}]
    assert ruled_out(rules, "split_payment", "New oven")
    assert not ruled_out(rules, "split_payment", "Flour")
    assert ruled_out([{"kind": "split_payment"}], "move_payment", "Rent")
    assert not ruled_out(rules, "owner_pay", "New oven")
