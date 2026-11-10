from aheadly.ai.guardrails import check_numbers, numbers_in_text

FACTS = {
    "current_balance": 8200,
    "lowest_balance": -4000,
    "lowest_date": "2026-12-14",
    "weeks_ahead": 5,
    "top_outflows": [{"label": "Supplier", "amount": 4000}],
}


def test_guardrail_accepts_numbers_from_facts_in_any_format():
    assert check_numbers("You have $8,200 today and may drop to -$4,000 in 5 weeks.", [FACTS]).passed


def test_guardrail_rejects_an_invented_number():
    result = check_numbers("You have $8,200 today and should save $1,350 by Friday.", [FACTS])
    assert not result.passed and result.unverified == [1350.0]


def test_guardrail_allows_small_counts_and_rounding():
    assert check_numbers("Two bills, about $4,010 in total, over 8 weeks.", [FACTS]).passed


def test_number_extraction_handles_thousands_and_k():
    assert numbers_in_text("$3,000 and 2.5k and 12%") == [3000.0, 2500.0, 12.0]
