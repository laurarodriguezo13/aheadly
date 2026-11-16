"""Bad surprises (roadmap 3.5; its own sub-tab under Ask Aheadly since R.2): four surprises built
from the business's own numbers, each tested on the forecast. Nothing is saved."""

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, start_page
from aheadly.ui.charts import scenario_chart
from aheadly.ui.components import chart_note, money, scenario_metrics, suggestion_cards

core = start_page(copy.SURPRISES_TITLE)
require_data(core)

# roadmap 3.5: four bad surprises built from the business's own numbers; on their own sub-tab
# since R.2 they run straight away (worked out once per forecast run)
with st.container(border=True):
    st.markdown(f"**{copy.STRESS_TITLE}**")
    st.caption(copy.STRESS_INTRO)
    with st.spinner(copy.STRESS_WORKING):
        tests = core.stress_tests()
    for test in tests:
        impact = test["impact"]
        with st.container(border=True):
            st.markdown(f"**{test['label']}**")
            st.caption(test["detail"])
            if test["verdict"] == "fine":
                st.success(copy.STRESS_FINE.format(lowest=money(impact["lowest_after"])))
            elif impact["lowest_before"] < test["low_cash_line"]:
                st.warning(copy.STRESS_SHORT_ALREADY.format(gap=money(test["gap"])))
            else:
                st.warning(copy.STRESS_SHORT.format(gap=money(test["gap"])))
            st.caption(
                copy.STRESS_IMPACT.format(
                    before=money(impact["lowest_before"]),
                    after=money(impact["lowest_after"]),
                    chance_before=impact["chance_before"],
                    chance_after=impact["chance_after"],
                )
            )
            # roadmap R.3: open a fix to change it or say no; it's tested with the surprise in place
            suggestion_cards(
                test["fixes"], f"stress-{test['key']}", test["label"], copy.STRESS_HELPS, test["adjustments"]
            )
            if st.button(copy.STRESS_CHART, key=f"stress-chart-{test['key']}"):
                st.session_state[f"stress-result-{test['key']}"] = core.stress_result(test["key"])
            shown = st.session_state.get(f"stress-result-{test['key']}")
            if shown is not None:
                st.plotly_chart(
                    scenario_chart(shown.baseline, shown.scenario, shown.low_cash_line),
                    width="stretch",
                    config={"displayModeBar": False},
                    key=f"stress-plot-{test['key']}",
                )
                chart_note(core.scenario_chart_summary(shown, what="surprise"))
                scenario_metrics(shown)
