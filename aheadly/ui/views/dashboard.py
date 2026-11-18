"""Dashboard (storyboard frame 3: always watching)."""

from datetime import date

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.charts import forecast_chart
from aheadly.ui.components import (
    glossary,
    alert_list_html,
    dismissed_words,
    chart_note,
    insight_heading,
    day,
    money,
    section_title,
    stat_card,
    statement_notice,
    weeks,
)

core = start_page(copy.DASHBOARD_TITLE)
require_data(core)
loaded = st.session_state.pop("data_loaded", None)  # roadmap 5.1: just came back with a saved file
if loaded:
    saved_on = day(date.fromisoformat(loaded["saved_on"])) if loaded["saved_on"] else "?"
    st.success(copy.LOADED.format(name=loaded["business_name"], saved_on=saved_on, n=loaded["transactions"]))

with st.spinner(copy.CHECKING_MONEY):
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
        when = copy.LOWEST_IS_TODAY if low_date is None else f"In {weeks(dash.lowest_weeks)}"
        if value < 0 and low_date is not None:  # roadmap R.1: below zero says what it means
            when = copy.SHORT_BY.format(short=money(-value), date=f"{low_date:%b} {low_date.day}")
        chance = copy.chance_words(dash.chance_pct)
        if chance:  # roadmap 3.1
            when = f"{when} · {chance}"
        below = value < business.low_cash_line
        stat_card(
            copy.LOWEST_PROJECTED,
            money(value),
            when,
            "red" if below else "teal",
            "rose" if below else "mint",
            "lowest_projected",
        )
with col3:
    if dash.next_payment:
        due, amount, label = dash.next_payment
        stat_card(copy.NEXT_PAYMENT, money(-amount), f"{label} · {due:%b %d}", "", "sky")

if forecast:  # roadmap 3.4: how much is safe to spend, and to pay yourself
    spend = core.safe_to_spend()
    pay = core.safe_owner_pay()
    col4, col5 = st.columns(2)
    with col4:
        if spend["amount"] > 0:
            sub = copy.SAFE_SPEND_SUB.format(line=money(spend["low_cash_line"]))
            stat_card(copy.SAFE_SPEND, money(spend["amount"]), sub, "teal", "mint", "safe_to_spend")
        else:
            sub = copy.SAFE_SPEND_NONE.format(worst=money(spend["lowest_worst_case"]))
            stat_card(copy.SAFE_SPEND, money(0), sub, "red", "rose", "safe_to_spend")
    with col5:
        if pay is None:
            stat_card(copy.SAFE_PAY, "?", copy.SAFE_PAY_UNKNOWN, "", "lav", "safe_pay")
            if core.questions_left() and st.button(copy.QUESTIONS_GO, key="dashboard-pay-questions"):
                go_to("questions")
        elif pay["safe"] > 0:
            sub = copy.SAFE_PAY_SUB.format(now=money(pay["now"]), how_often=pay["how_often"])
            stat_card(copy.SAFE_PAY, money(pay["safe"]), sub, "purple", "lav", "safe_pay")
        else:
            stat_card(
                copy.SAFE_PAY,
                money(0),
                copy.SAFE_PAY_NONE.format(now=money(pay["now"])),
                "red",
                "rose",
                "safe_pay",
            )

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
    chart_note(core.forecast_chart_summary())
    if st.button(copy.BASIS_LINK, key="dashboard-basis"):
        go_to("basis")
    trust = core.forecast_confidence()
    with st.container(border=True):  # R.1: the level once, what would help, the passed checks apart
        passed = [c for c in trust["checks"] if c.grade == 2]
        to_improve = [c for c in trust["checks"] if c.grade < 2]
        level = copy.CONFIDENCE_LEVELS[trust["level"]]
        count = copy.CONFIDENCE_COUNT.format(passed=len(passed), total=len(trust["checks"]))
        st.markdown(f"**{copy.CONFIDENCE_TITLE.format(level=level)}** · {count}")
        if to_improve:
            st.markdown(copy.CONFIDENCE_BETTER)
            st.markdown("\n".join(f"- {c.text}" for c in to_improve))
        if passed:
            with st.expander(copy.CONFIDENCE_PASSED.format(n=len(passed))):
                st.markdown("  \n".join(f"✓ {c.text}" for c in passed))
    if core.no_one_offs_planned():
        note, go = st.columns([4, 1])
        note.info(copy.NOTHING_PLANNED)
        if go.button(copy.NOTHING_PLANNED_GO, key="dashboard-nothing-planned"):
            go_to("basis")

if forecast:  # roadmap 4.3: the top things we noticed, the rest on the Insights page
    cards = core.noticed_cards()
    with st.container(border=True):
        section_title(copy.NOTICED_TITLE)
        if not cards:
            st.caption(copy.NOTICED_DASHBOARD_EMPTY)
        for card in cards[:3]:
            st.markdown(insight_heading(card), unsafe_allow_html=True)
            chart_note(card["body"])
        if cards and st.button(copy.NOTICED_MORE, key="dashboard-insights"):
            go_to("insights")

left, right = st.columns([1, 1])
with left, st.container(border=True):
    section_title(copy.UPCOMING_ALERTS)
    if dash.alerts:
        st.markdown(alert_list_html(dash.alerts), unsafe_allow_html=True)
        if st.button(copy.OPEN_ALERTS):
            go_to("alerts")
    elif dismissed := core.dismissed_alerts():
        st.info(copy.ONLY_DISMISSED.format(what=dismissed_words(dismissed)))
    else:
        st.success(copy.NO_ALERTS)
with right, st.container(border=True):
    section_title(copy.ASK_BOX)
    st.caption(copy.CHAT_INTRO)
    box, send = st.columns([3, 1])
    question = box.text_input(copy.ASK_BOX, placeholder=copy.ASK_PLACEHOLDER, label_visibility="collapsed")
    if send.button("Ask", type="primary", width="stretch") and question.strip():
        go_to("ask", question.strip())

glossary()  # roadmap 5.3
