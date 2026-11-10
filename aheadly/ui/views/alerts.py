"""Alerts (storyboard frame 4: early warning). Layout follows alert_detail_mockup.png."""

import html
from datetime import date

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.components import (
    banner,
    card,
    check_list_html,
    info_card,
    money,
    rows_html,
    severity_pill,
    weeks,
)

core = start_page(copy.ALERTS_TITLE)
require_data(core)

alerts = core.get_alerts()
if not alerts:
    st.success(copy.NO_ALERTS)


def why_it_matters(alert) -> str:
    facts = alert.facts
    if alert.type == "shortfall":
        total = sum(o["amount"] for o in facts["top_outflows"])
        return (
            f"Payments of {money(total)} land in the same week, and your balance would fall to "
            f"{money(facts['lowest_balance'])} around {date.fromisoformat(facts['lowest_date']):%b %d}, below your "
            f"{money(facts['low_cash_line'])} safety line."
        )
    return (
        f"Even in a bad case you keep {money(facts['lowest_worst_case'])}, more than three months "
        f"of outflows ({money(facts['three_months_of_outflows'])})."
    )


for alert in alerts:
    core.mark_alert_read(alert.id)
    card(
        f"{severity_pill(alert.severity)}<h3>{html.escape(alert.title)}</h3>"
        f'<p style="font-size:1.05rem">{html.escape(alert.body)}</p>',
        "lav",
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        info_card(copy.WHY_IT_MATTERS, f"<p>{html.escape(why_it_matters(alert))}</p>", "lav", icon="i")
    with c2:
        actions = [(a["label"], a.get("detail", "")) for a in alert.actions]
        info_card(copy.WHAT_YOU_CAN_DO, check_list_html(actions))
    with c3:
        outflows = [(o["label"], money(o["amount"])) for o in alert.facts.get("top_outflows", [])]
        if outflows:
            title = copy.TOP_OUTFLOWS.format(weeks=weeks(alert.weeks_ahead))
            info_card(title, rows_html(outflows), "sky")

    b1, b2, b3, _ = st.columns([1, 1, 1, 3])
    if b1.button(copy.SEE_WHY, key=f"why-{alert.id}", type="primary", width="stretch"):
        go_to("ask", f"Why do I have this alert: {alert.title}?")
    if b2.button(copy.TEST_WHAT_IF, key=f"whatif-{alert.id}", width="stretch"):
        go_to("whatif")
    if b3.button(copy.DISMISS, key=f"dismiss-{alert.id}", width="stretch"):
        core.dismiss_alert(alert.id)
        st.rerun()
    banner(copy.ALERT_FOOTER)
