"""What-if form (feature 4, form version). Same engine as the chat."""

import html
from datetime import timedelta

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, start_page
from aheadly.ui.charts import scenario_chart
from aheadly.ui.components import banner, scenario_metrics

core = start_page(copy.WHATIF_TITLE)
require_data(core)
st.caption(copy.WHATIF_INTRO)

labels = sorted({item.label for item in core.repo.list_scheduled_items(core.status().business.id)})

with st.form("whatif"):
    kind_label = st.selectbox("What do you want to test?", list(copy.WHATIF_TYPES))
    kind = copy.WHATIF_TYPES[kind_label]
    c1, c2 = st.columns(2)
    if kind == "one_time_expense":
        amount = c1.number_input("Amount ($)", min_value=1.0, value=2000.0, step=100.0, format="%.0f")
        day = c2.date_input("When?", value=core.today + timedelta(days=7))
        label = st.text_input("What is it?", value="New purchase")
        adjustment = {"type": kind, "amount": amount, "date": day.isoformat(), "label": label}
        name = f"Buy {label} ({amount:,.0f})"
    elif kind == "move_item":
        label = c1.selectbox("Which payment?", labels)
        day = c2.date_input("New date", value=core.today + timedelta(days=49))
        adjustment = {"type": kind, "label": label, "new_date": day.isoformat()}
        name = f"Move {label} to {day:%b %d}"
    else:
        percent = c1.slider("Sales change (%)", -30, 30, -10)
        day = c2.date_input("Starting", value=core.today)
        adjustment = {"type": kind, "percent": percent, "start_date": day.isoformat()}
        name = f"Sales {percent:+d}%"
    submitted = st.form_submit_button(copy.RUN_SCENARIO, type="primary")

if submitted:
    with st.spinner("Running the forecast again…"):
        try:
            result = core.run_what_if([adjustment], name)
        except ValueError as exc:
            st.error(f"That scenario did not work: {exc}")
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
            with st.spinner("Saving your plan…"):
                core.save_plan(result)
            st.session_state.pop("whatif_result", None)
            st.success(copy.PLAN_SAVED)

saved = core.saved_scenarios()
if saved:
    with st.expander("Scenario history"):
        for row in saved[:10]:
            flag = " · saved as plan" if row["saved_as_plan"] else ""
            st.write(
                f"**{row['name']}**{flag}: lowest base case "
                f"${row['result']['scenario']['lowest_base_case']:,} ({row['created_at'][:16]})"
            )
