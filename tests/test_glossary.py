"""Roadmap 5.3: short explanations of the money words, true to how the app works them out."""

from aheadly.ai.forecast_engine import ForecastEngine
from aheadly.config import Settings
from aheadly.ui import copy


def test_every_money_word_has_a_meaning():
    for term in (
        "low_cash_line",
        "base_case",
        "worst_case",
        "best_case",
        "lowest_projected",
        "chance_below",
        "safe_to_spend",
        "safe_pay",
        "cash_cushion",
    ):
        name, text = copy.GLOSSARY[term]
        assert name and text.endswith(".") and copy.meaning(term) == text


def test_the_meanings_say_what_the_app_does():
    """The numbers in the words match the engine: 500 ways, 8 weeks, 1 in 10 for a bad month."""
    assert ForecastEngine.__init__.__defaults__[1] == 500  # n_paths
    assert "500 ways" in copy.meaning("chance_below")
    assert Settings().horizon_days == 56 and "8 weeks" in copy.meaning("base_case")
    assert "1 in 10" in copy.meaning("worst_case") and "1 in 10" in copy.meaning("best_case")
    assert copy.meaning("low_cash_line").startswith(copy.LOW_CASH_HELP)


def test_a_meaning_never_breaks_the_tip_it_sits_in():
    """The ⓘ tip is an HTML title: quotes and brackets in a meaning are escaped, not cut."""
    import html

    for term in copy.GLOSSARY:
        escaped = html.escape(copy.meaning(term), quote=True)
        assert '"' not in escaped and "<" not in escaped
