"""What-if form (feature 4, form version). Same engine as the chat."""

import html
from datetime import timedelta

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, start_page
from aheadly.ui.charts import scenario_chart
from aheadly.ui.components import banner, local_time, money, scenario_metrics

core = start_page(copy.WHATIF_TITLE)
require_data(core)
st.caption(copy.WHATIF_INTRO)

labels = core.scheduled_labels()

# roadmap 3.5: one click, four bad surprises built from the business's own numbers
with st.container(border=True):
    st.markdown(f"**{copy.STRESS_TITLE}**")
    st.caption(copy.STRESS_INTRO)
    if st.button(copy.STRESS_RUN, key="stress-run"):
        st.session_state["stress_open"] = True
    if st.session_state.get("stress_open"):
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
                if test["fixes"]:
                    st.markdown(copy.STRESS_HELPS)
                    st.markdown(
                        "\n".join(
                            f"- {fix['label']}: "
                            + copy.STRESS_FIX_AFTER.format(after=money(fix["impact"]["lowest_after"]))
                            for fix in test["fixes"]
                        )
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
                    scenario_metrics(shown)

# outside the form, so the boxes below change as soon as the owner picks another kind
kind_label = st.selectbox(copy.WHATIF_PICK, list(copy.WHATIF_TYPES))
kind = copy.WHATIF_TYPES[kind_label]

with st.form("whatif"):
    c1, c2 = st.columns(2)
    if kind == "one_time_expense":
        amount = c1.number_input("Amount ($)", min_value=1.0, value=2000.0, step=100.0, format="%.0f")
        day = c2.date_input("When?", value=core.today + timedelta(days=7), format="MM/DD/YYYY")
        label = st.text_input(copy.WHATIF_WHAT, value=copy.WHATIF_DEFAULT_NAME)
        adjustment = {"type": kind, "amount": amount, "date": day.isoformat(), "label": label}
        name = f"Buy {label} ({amount:,.0f})"
    elif kind == "move_item":
        label = c1.selectbox("Which payment?", labels)
        day = c2.date_input("New date", value=core.today + timedelta(days=49), format="MM/DD/YYYY")
        adjustment = {"type": kind, "label": label, "new_date": day.isoformat()}
        name = f"Move {label} to {day:%b %d}"
    else:
        percent = c1.slider("Sales change (%)", -30, 30, -10)
        day = c2.date_input("Starting", value=core.today, format="MM/DD/YYYY")
        adjustment = {"type": kind, "percent": percent, "start_date": day.isoformat()}
        name = f"Sales {percent:+d}%"
    submitted = st.form_submit_button(copy.RUN_SCENARIO, type="primary")

if submitted:
    with st.spinner(copy.WHATIF_RUNNING):
        try:
            result = core.run_what_if([adjustment], name)
        except ValueError as exc:
            st.error(copy.WHATIF_FAILED.format(error=exc))
            st.stop()
        st.session_state["whatif_result"] = result
        st.session_state["whatif_text"] = core.explain_scenario(result)

result = st.session_state.get("whatif_result")
if result is not None:
    with st.container(border=True):
        st.subheader(result.name)
        st.plotly_chart(
            scenario_chart(result.baseline, result.scenario, result.low_cash_line),
            width="stretch",
            config={"displayModeBar": False},
        )
        scenario_metrics(result)
        banner(html.unescape(st.session_state.get("whatif_text", "")))
        if st.button(copy.SAVE_PLAN, type="primary"):
            with st.spinner(copy.SAVING_PLAN):
                core.save_plan(result)
            st.session_state.pop("whatif_result", None)
            st.success(copy.PLAN_SAVED)

saved = core.saved_scenarios()
if saved:
    with st.expander(copy.WHATIF_HISTORY):
        for row in saved[:10]:
            flag = " · saved as plan" if row["saved_as_plan"] else ""
            st.write(
                f"**{row['name']}**{flag}: lowest base case "
                f"{money(row['result']['scenario']['lowest_base_case'])} ({local_time(row['created_at'])})"
            )
