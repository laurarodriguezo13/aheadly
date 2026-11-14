"""Roadmap 4.2: words for each thing we noticed and a short summary under every chart.

Code works out every number and picks the titles; the model writes 1–3 sentences from the facts,
the guardrail checks each number, and the template stands in when it fails. Each text is written
once per facts, so Streamlit's reruns don't call the provider again.
"""

import json
from datetime import timedelta

import pytest

from aheadly.ai import templates
from aheadly.ai.guardrails import check_numbers
from aheadly.ai.insight_translator import InsightTranslator
from aheadly.ai.llm_client import LLMError, LLMReply
from tests.test_businesses import import_business

# one made-up insight of each kind, as pattern_rules.py returns them
INSIGHTS = [
    {
        "type": "thin_cushion",
        "facts": {"current_balance": 3568, "weekly_money_out": 2404, "weeks_covered": 1.5},
        "actions": ["build_buffer", "lower_owner_pay_for_a_while"],
    },
    {
        "type": "cost_creeping_up",
        "facts": {"category": "suppliers", "monthly_before": 3335, "monthly_now": 4127, "change_pct": 24},
        "actions": ["compare_suppliers", "raise_prices_to_cover"],
    },
    {
        "type": "costs_faster_than_sales",
        "facts": {
            "costs_change_pct": 10,
            "sales_change_pct": -4,
            "monthly_costs_now": 9100,
            "monthly_sales_now": 9494,
        },
        "actions": ["review_prices", "renegotiate_with_suppliers"],
    },
    {
        "type": "net_flow_shrinking",
        "facts": {"monthly_net_before": -128, "monthly_net_now": -1047},
        "actions": ["review_prices", "cut_a_cost"],
    },
    {
        "type": "owner_pay_high",
        "facts": {"monthly_owner_pay": 1300, "monthly_left_before_pay": 1651, "share_pct": 79},
        "actions": ["lower_owner_pay_for_a_while"],
    },
    {
        "type": "owner_pay_high",
        "facts": {"monthly_owner_pay": 850, "monthly_left_before_pay": 263, "share_pct": 324},
        "actions": ["lower_owner_pay_for_a_while"],
    },
    {
        "type": "few_customers",
        "facts": {
            "customer": "TRANSF RECIBIDA CONSTRUCTORA ANDINA SAS",
            "share_pct": 30,
            "amount_6_months": 50928,
        },
        "actions": ["find_another_customer", "ask_for_deposits"],
    },
    {
        "type": "customers_paying_later",
        "facts": {
            "customer": "TRANSF RECIBIDA CONSTRUCTORA ANDINA SAS",
            "days_between_now": 35,
            "days_between_before": 30,
            "last_paid": "2026-10-20",
        },
        "actions": ["send_reminder", "shorten_terms"],
    },
    {
        "type": "duplicate_charge",
        "facts": {"payee": "PAGO PSE LACTEOS DEL VALLE", "amount": 172.23, "date": "2026-10-20"},
        "actions": ["ask_for_refund"],
    },
    {
        "type": "unusual_charge",
        "facts": {"payee": "COMPRA INTERNACIONAL MKTPLACE", "amount": 689.3, "date": "2026-10-27"},
        "actions": ["check_the_charge"],
    },
    {
        "type": "new_recurring_charge",
        "facts": {"payee": "Loggro pos sas", "amount": 34.9, "how_often": "monthly", "since": "2026-08-18"},
        "actions": ["cancel_if_not_needed"],
    },
    {
        "type": "sales_slowing",
        "facts": {"monthly_sales_before": 12000, "monthly_sales_now": 9800, "change_pct": -18},
        "actions": ["promotion_on_slow_days"],
    },
    {
        "type": "idle_cash",
        "facts": {"lowest_worst_case": 49868, "three_months_of_outflows": 27786, "horizon_weeks": 8},
        "actions": ["pay_supplier_early_for_discount", "buy_inventory_in_bulk"],
    },
]

FORECAST = {
    "chart": "forecast",
    "weeks": 8,
    "balance_weeks_ago": 5485,
    "balance_today": 8200,
    "lowest_base_case": -926,
    "lowest_date": "2026-12-15",
    "lowest_worst_case": -2395,
    "end_base_case": 10908,
    "low_cash_line": 2000,
    "risk_level": "act_now",
    "chance_below_line_pct": 100,
    "payment_before_lowest": {"label": "Quarterly flour order", "amount": 4000, "date": "2026-12-15"},
}


class _Model:
    name = "fake"

    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.calls = reply, fail, []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        if self.fail:
            raise LLMError("provider down")
        return LLMReply(content=json.dumps(self.reply))


def _translator(model) -> InsightTranslator:
    return InsightTranslator(model, tools=None)


def _sentences(text: str) -> int:
    return text.count(". ") + 1


# ------------------------------------------------------------- templates
@pytest.mark.parametrize("insight", INSIGHTS, ids=lambda i: i["type"])
def test_every_kind_has_short_words_with_only_its_own_numbers(insight):
    facts = templates.readable_insight(insight)
    title, body = templates.insight_title(facts), templates.insight_body(facts)
    assert title and body != "Something in your statement is worth a look."
    assert check_numbers(f"{title} {body}", [facts]).passed, body
    assert len(body.split()) <= 60 and _sentences(body) <= 3
    assert len(templates.insight_actions(insight["actions"])) == len(insight["actions"])


def test_payee_names_lose_the_bank_wording():
    assert templates.payee_name("TRANSF RECIBIDA CAFE MOLIENDA AZUL") == "Cafe Molienda Azul"
    assert templates.payee_name("PAGO PSE LACTEOS DEL VALLE") == "Lacteos Del Valle"
    assert templates.payee_name("COMPRA GODADDY.COM") == "Godaddy.com"
    assert templates.payee_name("Flour and dairy") == "Flour and dairy"  # the owner's own words stay
    assert templates.payee_name("TRANSF 0045 REF 88213") == "Transf 0045 Ref 88213"  # nothing left: kept


def test_payments_found_in_the_statement_are_called_by_what_they_are():
    """Live check, 2026-11-13: the alert said "Pago nomina"."""
    assert templates.payment_name("Pago nomina", "payroll", from_statement=True) == "Payroll"
    assert templates.payment_name("Transf a cta ahorros m gomez", "owner_pay", True) == "Your own pay"
    assert templates.payment_name("Pago pse molinos el trigal", "suppliers", True) == "Molinos El Trigal"
    assert templates.payment_name("Christmas ingredients", "suppliers", False) == "Christmas ingredients"


def test_owner_pay_above_what_the_business_makes_is_said_plainly():
    facts = templates.readable_insight(INSIGHTS[5])
    body = templates.insight_body(facts)
    assert "324%" not in body and "cash you already had" in body


def test_chart_summaries_use_only_the_chart_numbers():
    text = templates.chart_summary(FORECAST)
    assert check_numbers(text, [FORECAST]).passed and _sentences(text) <= 3
    assert "Quarterly flour order" in text and "below your $2,000 line" in text
    watch = {**FORECAST, "risk_level": "watch", "lowest_base_case": 2600, "lowest_worst_case": 1200}
    assert "could dip to $1,200" in templates.chart_summary(watch)
    flat = {**FORECAST, "end_base_case": -926}  # the lowest point is the last day
    assert "still there at the end" in templates.chart_summary(flat)


# ------------------------------------------------------------- the model, the guardrail, the cache
def test_the_model_writes_the_body_and_code_the_title():
    model = _Model({"body": "Lacteos Del Valle took $172.23 twice on Oct 20. Worth asking for it back."})
    text = _translator(model).write_insight(INSIGHTS[8])
    assert text.title == "A charge that looks doubled"
    assert text.body.startswith("Lacteos Del Valle took $172.23")
    assert [a["label"] for a in text.actions] == ["Ask for a refund"]
    sent = json.loads(model.calls[0][-1]["content"][len("WRITE_INSIGHT") :])
    assert sent["payee"] == "Lacteos Del Valle"  # the model sees the clean name, not the bank's wording


def test_an_invented_number_falls_back_to_the_template():
    model = _Model({"body": "Lacteos Del Valle took $350 twice."})
    text = _translator(model).write_insight(INSIGHTS[8])
    assert text.body == templates.insight_body(templates.readable_insight(INSIGHTS[8]))


def test_a_provider_that_is_down_falls_back_to_the_template():
    text = _translator(_Model(fail=True)).summarize_chart(FORECAST)
    assert text == templates.chart_summary(FORECAST)


def test_each_text_is_written_once_per_facts():
    model = _Model({"summary": "Your cash dips to -$926 around Dec 15, below your $2,000 line."})
    translator = _translator(model)
    first = translator.summarize_chart(FORECAST)
    assert translator.summarize_chart(dict(FORECAST)) == first and len(model.calls) == 1
    translator.summarize_chart({**FORECAST, "balance_today": 8300})  # new numbers: written again
    assert len(model.calls) == 2


# ------------------------------------------------------------- App Core
@pytest.fixture(scope="module")
def bakery():
    return import_business("panaderia-la-esquina", with_one_offs=True)  # questions answered


def test_insight_cards_have_a_title_words_and_actions(bakery):
    cards = bakery.insight_cards()
    assert [c["type"] for c in cards] == ["owner_pay_high"]
    card = cards[0]
    assert card["title"] == "Your pay takes most of what's left"
    assert card["body"] and card["actions"][0]["label"] == "Take a little less for a while"


def test_dashboard_chart_summary_matches_the_forecast(bakery):
    facts = bakery.forecast_chart_facts()
    summary = bakery.forecast_chart_summary()
    assert facts["risk_level"] == "act_now"
    assert check_numbers(summary, [facts]).passed and "below your $2,000 line" in summary


def test_alerts_name_payments_by_what_they_are(bakery):
    labels = [o["label"] for a in bakery.get_alerts() for o in a.facts["top_outflows"]]
    assert "Pago nomina" not in labels and "Payroll" in labels
    assert "Quarterly flour order" in labels  # the owner's own name stays


def test_what_if_chart_summary(bakery):
    item = next(i for i in bakery.repo.list_scheduled_items(1) if i.status == "user" and i.amount < 0)
    new_date = (item.due_date + timedelta(days=7)).isoformat()
    result = bakery.run_what_if(
        [{"type": "move_item", "label": item.label, "new_date": new_date}], name=f"Move {item.label}"
    )
    text = bakery.scenario_chart_summary(result)
    assert text.startswith("With this change the lowest point is about")
    assert check_numbers(text, [result.summary()]).passed


def test_scenario_summary_says_whether_the_change_crosses_the_line():
    def facts(base: int, scen: int) -> dict:
        side = {"lowest_date": "2026-12-15", "lowest_worst_case": scen - 1000, "chance_below_line_pct": 50}
        return {
            "chart": "scenario",
            "what": "surprise",
            "scenario_name": "Surprise bill",
            "low_cash_line": 2000,
            "baseline": {**side, "lowest_base_case": base},
            "scenario": {**side, "lowest_base_case": scen},
        }

    assert "takes you below your $2,000 line" in templates.chart_summary(facts(2600, 1400))
    assert "still below your $2,000 line" in templates.chart_summary(facts(1400, 900))
    assert templates.chart_summary(facts(1400, 900)).startswith("With this surprise")


def test_stress_tests_name_the_supplier_without_the_bank_wording(bakery):
    supplier = next(t for t in bakery.stress_tests() if t["key"] == "supplier_up")
    assert supplier["detail"].startswith("Molinos El Trigal: ")
