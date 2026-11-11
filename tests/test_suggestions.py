"""Suggested questions come from the business's own payments, and the offline chat understands them."""

from aheadly.ai.llm_client import StubClient
from tests.conftest import TODAY

LABELS = ["New oven", "Quarterly flour order (Molinos del Sur)"]


def test_biggest_upcoming_payment_is_the_oven_for_the_demo_bakery(connected_core):
    assert connected_core.biggest_upcoming_payment() == "New oven"


def test_offline_chat_moves_the_payment_the_question_names():
    question = "What if I move the quarterly flour order (Molinos del Sur) payment to next month?"
    call = StubClient(TODAY).plan(question, LABELS)
    assert call.name == "run_scenario"
    assert call.arguments["adjustments"][0]["label"] == "Quarterly flour order (Molinos del Sur)"


def test_offline_chat_matches_most_of_the_words():
    call = StubClient(TODAY).plan("What if I pay the flour order next month instead?", LABELS)
    assert call.arguments["adjustments"][0]["label"] == "Quarterly flour order (Molinos del Sur)"


def test_suggested_question_runs_a_what_if(connected_core):
    name = connected_core.biggest_upcoming_payment()
    answer = connected_core.ask(f"What if I move the {name.lower()} payment to next month?")
    assert answer.scenario is not None
