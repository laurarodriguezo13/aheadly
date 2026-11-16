"""Alerts (storyboard frame 4: early warning). Layout follows alert_detail_mockup.png."""

import html
from datetime import date

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.components import (
    banner,
    card,
    dismissed_words,
    info_card,
    money,
    rows_html,
    severity_pill,
    suggestion_cards,
    weeks,
)

core = start_page(copy.ALERTS_TITLE)
require_data(core)

alerts = core.get_alerts()


def why_it_matters(alert) -> str:
    facts = alert.facts
    if alert.type == "shortfall":
        total = sum(o["amount"] for o in facts["top_outflows"])
        when = f"{date.fromisoformat(facts['lowest_date']):%b} {date.fromisoformat(facts['lowest_date']).day}"
        if facts["lowest_balance"] < 0:  # R.1: below zero says what it means
            return copy.WHY_BELOW_ZERO.format(
                total=money(total), short=money(-facts["lowest_balance"]), date=when
            )
        return copy.WHY_SHORTFALL.format(
            total=money(total),
            lowest=money(facts["lowest_balance"]),
            date=when,
            line=money(facts["low_cash_line"]),
        )
    if alert.type == "watch":
        when = f"{date.fromisoformat(facts['lowest_date']):%b} {date.fromisoformat(facts['lowest_date']).day}"
        return copy.WHY_WATCH.format(
            line=money(facts["low_cash_line"]), worst=money(facts["lowest_worst_case"]), date=when
        )
    if alert.type in ("duplicate_charge", "unusual_charge"):
        return copy.WHY_CHARGE[alert.type]
    return copy.WHY_IDLE.format(
        worst=money(facts["lowest_worst_case"]), three_months=money(facts["three_months_of_outflows"])
    )


if not alerts:  # "watch" has its own alert now (roadmap R.1), so nothing open means nothing to do
    dismissed = core.dismissed_alerts()
    if dismissed:
        st.info(copy.ONLY_DISMISSED.format(what=dismissed_words(dismissed)))
        if st.button(copy.BRING_BACK):
            core.bring_back_alerts()
            st.rerun()
    else:
        st.success(copy.NO_ALERTS)

financing_shown = False
for alert in alerts:
    card(
        f"{severity_pill(alert.severity, alert.type == 'shortfall' and alert.facts['lowest_balance'] < 0)}<h3>{html.escape(alert.title)}</h3>"
        f'<p style="font-size:1.05rem">{html.escape(alert.body)}</p>',
        "lav",
    )
    # R.1: the alert's own buttons right under it, so it's clear what they're about
    with st.container(horizontal=True):
        if st.button(copy.ASK_ABOUT_ALERT, key=f"why-{alert.id}", type="primary"):
            go_to("ask", copy.ASK_ABOUT_ALERT_QUESTION.format(title=alert.title))
        if st.button(copy.DISMISS, key=f"dismiss-{alert.id}"):
            core.dismiss_alert(alert.id)
            st.rerun()

    outflows = [(o["label"], money(o["amount"])) for o in alert.facts.get("top_outflows", [])]
    c1, c2 = st.columns(2)
    with c1:
        info_card(copy.WHY_IT_MATTERS, f"<p>{html.escape(why_it_matters(alert))}</p>", "lav", icon="i")
    if outflows:
        with c2:
            title = copy.TOP_OUTFLOWS.format(weeks=weeks(alert.weeks_ahead))
            info_card(title, rows_html(outflows), "sky")

    suggestion_cards(alert.actions, f"action-{alert.id}", alert.title)
    if alert.type in ("shortfall", "watch") and not financing_shown:
        # roadmap R.2: the financing helper has its own sub-tab; the alert says when it's needed
        short = core.still_short()
        if short:
            st.warning(copy.STILL_SHORT.format(gap=money(short)))
        if st.button(copy.FIN_SEE, key=f"financing-{alert.id}", type="primary" if short else "secondary"):
            go_to("financing")
        financing_shown = True
if alerts:
    banner(copy.ALERT_FOOTER)
