"""Issue 14 (with 26 and 33): App Core split by area, and the dashboard asking App Core only."""

from pathlib import Path

from aheadly.core import areas
from aheadly.core.app_core import AppCore
from tests.test_businesses import import_business

CORE = Path(AppCore.__module__.replace(".", "/") + ".py")


def test_app_core_is_split_into_areas_of_a_readable_size():
    folder = Path(areas.__file__).parent
    for path in [CORE, *folder.glob("*.py")]:
        assert len(path.read_text(encoding="utf-8").splitlines()) < 700, path
    for name in ("FilesMixin", "QuestionsMixin", "BasisMixin", "SuggestionsMixin", "InsightsMixin"):
        assert name in {base.__name__ for base in AppCore.__mro__}


def test_methods_only_tests_used_are_gone():
    for name in ("answer_payee", "end_plan_item"):
        assert not hasattr(AppCore, name)


def test_the_dashboard_gets_its_words_from_app_core():
    cafe = import_business("cafe-la-tertulia", with_one_offs=True)
    dash = cafe.get_dashboard()
    assert dash.next_payment[2] == "Payroll"  # not the bank's "Pago nomina"
    assert dash.lowest_weeks >= 1 and 0 <= dash.chance_pct <= 100
    page = Path("aheadly/ui/views/dashboard.py").read_text(encoding="utf-8")
    assert "alert_rules" not in page
