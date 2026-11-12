"""Dashboard (storyboard frame 3: always watching)."""

import streamlit as st

from aheadly.core import alert_rules
from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.charts import forecast_chart
from aheadly.ui.components import (
    alert_list_html,
    day,
    money,
    section_title,
    stat_card,
    statement_notice,
    weeks,
)

core = start_page(copy.DASHBOARD_TITLE)
require_data(core)

with st.spinner("Checking your money…"):
    core.ensure_fresh()
dash = core.get_dashboard()
forecast, business = dash.forecast, dash.business
lag = core.statement_lag_days()
statement_notice(core.statement_end(), core.today, lag, business.name if core.example() else None)
left = core.questions_left()
if left:
    note, go = st.columns([4, 1])
    note.info(copy.QUESTIONS_BANNER.format(n=left))
    if go.button(copy.QUESTIONS_GO, key="dashboard-questions"):
        go_to("questions")

col1, col2, col3 = st.columns(3)
with col1:
    when = copy.ON_STATEMENT_DAY.format(end=day(core.statement_end())) if lag else copy.AVAILABLE_TODAY
    stat_card(copy.CURRENT_CASH, money(dash.balance), when, "purple", "lav")
with col2:
    if forecast:
        value, low_date = forecast.lowest_with_today()
        when = (
            copy.LOWEST_IS_TODAY
            if low_date is None
            else f"In {weeks(alert_rules.weeks_until(core.today, low_date))}"
        )
        chance = copy.chance_words(alert_rules.chance_pct(forecast.chance_below(business.low_cash_line)))
        if chance:  # roadmap 3.1
            when = f"{when} · {chance}"
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
        due, amount, label = dash.next_payment
        stat_card(copy.NEXT_PAYMENT, money(-amount), f"{label} · {due:%b %d}", "", "sky")

with st.container(border=True):
    section_title(copy.CHART_TITLE)
    st.plotly_chart(
        forecast_chart(
            dash.history,
            forecast,
            business.low_cash_line,
            core.today,
            dash.balance,
            copy.CHART_FORECAST_STARTS if lag else "Today",
        ),
        width="stretch",
        config={"displayModeBar": False},
    )
    if st.button(copy.BASIS_LINK, key="dashboard-basis"):
        go_to("basis")
    trust = core.forecast_confidence()
    with st.container(border=True):
        st.markdown(f"**{copy.CONFIDENCE_TITLE.format(level=copy.CONFIDENCE_LEVELS[trust['level']])}**")
        st.markdown("\n".join(f"- {reason}" for reason in trust["reasons"]))
        with st.expander(copy.CONFIDENCE_ALL):
            st.markdown("\n".join(f"- {'✓' if c.grade == 2 else '•'} {c.text}" for c in trust["checks"]))
    if core.no_one_offs_planned():
        note, go = st.columns([4, 1])
        note.info(copy.NOTHING_PLANNED)
        if go.button(copy.NOTHING_PLANNED_GO, key="dashboard-nothing-planned"):
            go_to("basis")

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
        if st.button(copy.SEE_FIXES, key="dashboard-fixes"):  # roadmap 3.3
            go_to("alerts")
    else:
        st.success(copy.NO_ALERTS)
with right, st.container(border=True):
    section_title(copy.ASK_BOX)
    st.caption(copy.CHAT_INTRO)
    box, send = st.columns([3, 1])
    question = box.text_input(copy.ASK_BOX, placeholder=copy.ASK_PLACEHOLDER, label_visibility="collapsed")
    if send.button("Ask", type="primary", width="stretch") and question.strip():
        go_to("ask", question.strip())
