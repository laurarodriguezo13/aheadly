"""Roadmap 2.4: "Just say it". The owner's own words become plan items, saved only on Add."""

from __future__ import annotations

from datetime import date

import pytest

from aheadly.ai.llm_client import LLMError, LLMReply, ToolCall
from aheadly.ai.plan_text import amounts_in, check_item, dates_in, read_by_rules

from .test_example_business import _core

TODAY = date(2026, 11, 11)


def _one(text: str):
    items = read_by_rules(text, TODAY)
    assert len(items) == 1, items
    return items[0]


# ------------------------------------------------------------- reading amounts and dates
@pytest.mark.parametrize(
    "text, amounts",
    [
        ("$7,500", [7500.0]),
        ("$3,883.34", [3883.34]),
        ("$ 2.000", [2000.0]),
        ("$1.250,50", [1250.5]),
        ("USD 950", [950.0]),
        ("3.200 dólares", [3200.0]),
        ("$7.5k", [7500.0]),
        ("12 boxes and 3 people", []),  # numbers without money words are not amounts
    ],
)
def test_amounts(text, amounts):
    assert amounts_in(text) == pytest.approx(amounts)


@pytest.mark.parametrize(
    "text, dates",
    [
        ("on Nov 14", [date(2026, 11, 14)]),
        ("paid Dec 16 and 17", [date(2026, 12, 16), date(2026, 12, 17)]),
        ("el 20 de noviembre", [date(2026, 11, 20)]),
        ("on 2026-12-02", [date(2026, 12, 2)]),
        ("on 15/12", [date(2026, 12, 15)]),
        ("early December", [date(2026, 12, 5)]),
        ("late January", [date(2027, 1, 28)]),
        ("on Nov 3", [date(2027, 11, 3)]),  # already past this year: next year's
        ("for September-October", []),  # a month alone is not a day
    ],
)
def test_dates(text, dates):
    assert dates_in(text, TODAY)[0] == dates


# ------------------------------------------------------------- whole sentences
def test_a_purchase():
    item = _one("I'm buying a new oven for $7,500 on Nov 14")
    assert (item.label, item.direction, item.amount, item.due_date, item.certainty, item.ready) == (
        "New oven",
        "out",
        7500.0,
        date(2026, 11, 14),
        "confirmed",
        True,
    )


def test_money_owed_to_the_owner_is_income():
    item = _one("Constructora Prueba owes me $3,883.34 for Christmas hampers, due Nov 12")
    assert (item.direction, item.amount, item.due_date) == ("in", 3883.34, date(2026, 11, 12))
    assert item.label == "Constructora Prueba – Christmas hampers"
    assert _one("Café El Tinto Feliz owes me about $800, due Nov 28").label == "Café El Tinto Feliz"
    assert _one("Don Pedro me debe $500 el 30 de noviembre").label == "Don Pedro"


def test_each_on_two_days_is_two_items():
    items = read_by_rules("Both cafés ordered Christmas baskets: $5,500 each, paid Dec 16 and 17", TODAY)
    assert [(i.direction, i.amount, i.due_date) for i in items] == [
        ("in", 5500.0, date(2026, 12, 16)),
        ("in", 5500.0, date(2026, 12, 17)),
    ]


def test_about_makes_it_a_maybe_and_order_is_not_ordered():
    assert _one("Christmas ingredients, about $2,640.00, on Dec 10").certainty == "maybe"
    assert _one("The quarterly flour order of $4,000 is due Dec 15").direction == "out"


def test_several_things_in_one_message():
    items = read_by_rules(
        "New laptop $1,650 on Dec 2. A customer owes me $3,200 on Nov 30; rent $900 monthly on Dec 15", TODAY
    )
    assert [(i.direction, i.amount, i.repeats) for i in items] == [
        ("out", 1650.0, "once"),
        ("in", 3200.0, "once"),
        ("out", 900.0, "monthly"),
    ]


def test_what_is_missing_is_asked_not_guessed():
    assert _one("The staff's December bonus before Dec 20").problem == "How much?"
    assert _one("A new fridge for $1,200").problem == "When?"
    assert read_by_rules("Things are going well this month", TODAY) == []


def test_checks():
    raw = {"label": "Oven", "amount": 7500, "direction": "out", "date": "2026-11-14"}
    assert check_item(raw, TODAY).ready
    assert check_item({**raw, "date": "2026-10-01"}, TODAY).problem == "That date has already passed."
    assert check_item({**raw, "amount": -5}, TODAY).problem is None  # a sign is ignored: direction decides
    assert check_item({**raw, "amount": 0}, TODAY).problem == "How much?"
    assert check_item({**raw, "label": " "}, TODAY).problem == "Give it a name."
    assert check_item({**raw, "direction": "sideways"}, TODAY).direction == "out"
    # an amount the owner never wrote (a model's guess) is flagged
    assert check_item(raw, TODAY, "buying an oven next week").problem.startswith("We couldn't find")


# ------------------------------------------------------------- through App Core
def test_parsing_saves_nothing_and_add_saves_and_reforecasts():
    core = _core()
    core.load_example()
    before = len(core.planned_items())
    lowest_before = core.get_dashboard().forecast.lowest_with_today()[0]
    items = core.parse_plan_text("I'm buying a laptop for $1,650 on Dec 2")
    assert len(core.planned_items()) == before
    assert core.add_plan_items(items) == 1
    planned = {p["description"]: p for p in core.planned_items()}
    assert planned["Laptop"]["amount"] == -1650.0 and planned["Laptop"]["date"] == "2026-12-02"
    assert core.get_dashboard().forecast.lowest_with_today()[0] < lowest_before


def test_add_refuses_an_item_with_a_problem():
    core = _core()
    core.load_example()
    items = core.parse_plan_text("A new fridge for $1,200")
    with pytest.raises(ValueError, match="When"):
        core.add_plan_items(items)
    edited = [{**items[0].to_dict(), "due_date": "2026-12-01"}]
    assert core.add_plan_items(edited) == 1


def test_the_chat_proposes_and_never_saves():
    core = _core()
    core.load_example()
    before = len(core.planned_items())
    answer = core.ask("I'm buying a laptop for $1,650 on Dec 2")
    assert answer.tool_names == ["propose_plan_items"]
    assert [(p.label, p.amount) for p in answer.proposals] == [("Laptop", 1650.0)]
    assert "isn't saved yet" in answer.text and "Dec 2" in answer.text
    assert len(core.planned_items()) == before
    assert core.ask("When is my rent due?").proposals == []  # a question is not a plan


class _FakeModel:
    """Stands in for Gemini: answers with a tool call (or fails)."""

    name = "fake"

    def __init__(self, items=None, fail=False):
        self.items, self.fail, self.seen = items, fail, []

    def chat(self, messages, tools=None):
        self.seen.append(messages)
        if self.fail:
            raise LLMError("quota")
        return LLMReply(tool_calls=[ToolCall("1", "propose_plan_items", {"items": self.items})])


def _with_model(model):
    core = _core()
    core.load_example()
    core.translator._llm = model
    return core


def test_the_model_reads_it_and_code_checks_it():
    model = _FakeModel(
        [
            {
                "label": "Laptop for Isabela",
                "amount": 1650,
                "direction": "out",
                "date": "2026-12-02",
                "certainty": "maybe",
            },
            {"label": "Mouse", "amount": 40, "direction": "out", "date": "2026-12-02"},  # never written
        ]
    )
    core = _with_model(model)
    items = core.parse_plan_text("I'm buying a laptop for Isabela, about $1,650, on Dec 2")
    assert (items[0].label, items[0].certainty, items[0].ready) == ("Laptop for Isabela", "maybe", True)
    assert not items[1].ready
    assert model.seen[0][-1]["content"] == "I'm buying a laptop for Isabela, about $1,650, on Dec 2"


def test_rules_take_over_when_the_model_fails_or_finds_nothing():
    for model in (_FakeModel(fail=True), _FakeModel(items=[])):
        items = _with_model(model).parse_plan_text("I'm buying a new oven for $7,500 on Nov 14")
        assert [(i.label, i.amount) for i in items] == [("New oven", 7500.0)]
