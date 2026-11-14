"""Insights (roadmap 4.3): things we noticed, with what could help, and the month-by-month charts."""

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, start_page
from aheadly.ui.charts import cushion_chart, income_chart, money_in_out_chart, spending_chart
from aheadly.ui.components import action_rows, chart_note, insight_heading, section_title

core = start_page(copy.INSIGHTS_TITLE)
require_data(core)
st.caption(copy.INSIGHTS_INTRO)

section_title(copy.NOTICED_TITLE)
with st.spinner(copy.CHECKING_MONEY):
    cards = core.insight_cards()
if not cards:
    st.success(copy.NOTICED_NONE)
for i, card in enumerate(cards):
    with st.container(border=True):
        st.markdown(insight_heading(card), unsafe_allow_html=True)
        chart_note(card["body"])
        action_rows(core, card["actions"], f"insight-{i}", title=copy.NOTICED_HELP)

section_title(copy.INSIGHT_CHARTS_TITLE)
charts = core.insight_charts()
if not charts:
    st.info(copy.INSIGHTS_TOO_SHORT)
else:
    tabs = st.tabs([copy.INSIGHT_TABS[k] for k in charts])
    draw = {
        "money_in_out": lambda c: money_in_out_chart(c["rows"]),
        "spending": lambda c: spending_chart(c["names"], c["rows"]),
        "cushion": lambda c: cushion_chart(c["rows"], c["facts"]["target_weeks"]),
        "income_sources": lambda c: income_chart(c["rows"]),
    }
    for tab, (kind, chart) in zip(tabs, charts.items()):
        with tab:
            st.caption(copy.INSIGHT_CHART_NOTES[kind])
            st.plotly_chart(draw[kind](chart), width="stretch", config={"displayModeBar": False}, key=kind)
            chart_note(chart["summary"])
