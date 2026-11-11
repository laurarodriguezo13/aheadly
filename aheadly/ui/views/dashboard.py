"""Dashboard (storyboard frame 3: always watching)."""

import streamlit as st

from aheadly.core import alert_rules
from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.charts import forecast_chart
from aheadly.ui.components import alert_list_html, money, section_title, stat_card, weeks

core = start_page(copy.DASHBOARD_TITLE)
require_data(core)

with st.spinner("Checking your money…"):
    core.ensure_fresh()
dash = core.get_dashboard()
forecast, business = dash.forecast, dash.business

col1, col2, col3 = st.columns(3)
with col1:
    stat_card(copy.CURRENT_CASH, money(dash.balance), copy.AVAILABLE_TODAY, "purple", "lav")
with col2:
    if forecast:
        value, low_date = forecast.lowest_with_today()
        when = (
            copy.LOWEST_IS_TODAY
            if low_date is None
            else f"In {weeks(alert_rules.weeks_until(core.today, low_date))}"
        )
        below = value < business.low_cash_line
        stat_card(
            copy.LOWEST_PROJECTED,
            money(value),
            when,
            "red" if below else "teal",
            "rose" if below else "mint",
        )
with col3:
    if dash.next_payment:
        day, amount, label = dash.next_payment
        stat_card(copy.NEXT_PAYMENT, money(-amount), f"{label} · {day:%b %d}", "", "sky")

with st.container(border=True):
    section_title(copy.CHART_TITLE)
    st.plotly_chart(
        forecast_chart(dash.history, forecast, business.low_cash_line, core.today, dash.balance),
        width="stretch",
        config={"displayModeBar": False},
    )

left, right = st.columns([1, 1])
with left, st.container(border=True):
    section_title(copy.UPCOMING_ALERTS)
    if dash.alerts:
        st.markdown(alert_list_html(dash.alerts), unsafe_allow_html=True)
        if st.button("Open alerts"):
            go_to("alerts")
    elif forecast and forecast.risk_level(business.low_cash_line) == "watch":
        st.warning(
            copy.WATCH_NO_ALERTS.format(worst=money(forecast.min_p10), line=money(business.low_cash_line))
        )
    else:
        st.success(copy.NO_ALERTS)
with right, st.container(border=True):
    section_title(copy.ASK_BOX)
    st.caption(copy.CHAT_INTRO)
    box, send = st.columns([3, 1])
    question = box.text_input(copy.ASK_BOX, placeholder=copy.ASK_PLACEHOLDER, label_visibility="collapsed")
    if send.button("Ask", type="primary", width="stretch") and question.strip():
        go_to("ask", question.strip())
