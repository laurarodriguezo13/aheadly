"""Alerts (storyboard frame 4: early warning). Layout follows alert_detail_mockup.png."""

import html
from datetime import date

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.charts import scenario_chart
from aheadly.ui.components import (
    banner,
    card,
    check_list_html,
    info_card,
    money,
    rows_html,
    scenario_metrics,
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


def impact_line(impact: dict) -> str:
    risk = copy.RISK_NAMES
    return copy.ACTION_IMPACT.format(
        before=money(impact["lowest_before"]),
        after=money(impact["lowest_after"]),
        risk_before=risk[impact["risk_before"]],
        risk_after=risk[impact["risk_after"]],
        chance_before=impact["chance_before"],
        chance_after=impact["chance_after"],
    )


def action_rows(alert) -> None:
    """Roadmap 3.2: each action with what it changes, Test this, how to do it and a message to send."""
    if not any(a.get("how_to") for a in alert.actions):
        return
    st.markdown(f"**{copy.ACTIONS_TITLE}**")
    for i, action in enumerate(alert.actions):
        key = f"action-{alert.id}-{i}"
        with st.container(border=True):
            st.markdown(f"**{action['label']}**  \n{action.get('detail', '')}")
            if action.get("impact"):
                st.caption(impact_line(action["impact"]))
            else:
                st.caption(copy.ACTION_GENERAL)
            with st.expander(copy.ACTION_HOW):
                st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(action.get("how_to", []), 1)))
                if action.get("adjustment"):
                    if st.button(copy.ACTION_DRAFT, key=f"{key}-draft"):
                        st.session_state[f"{key}-message"] = core.draft_message(alert.id, i)
                    if st.session_state.get(f"{key}-message"):
                        st.code(st.session_state[f"{key}-message"], language=None, wrap_lines=True)
                        st.caption(copy.ACTION_DRAFT_NOTE)
            if action.get("adjustment"):
                if st.button(copy.ACTION_TEST, key=f"{key}-test", type="primary"):
                    st.session_state[f"{key}-result"] = core.run_what_if(
                        [action["adjustment"]], name=action["label"]
                    )
                result = st.session_state.get(f"{key}-result")
                if result is not None:
                    st.plotly_chart(
                        scenario_chart(result.baseline, result.scenario, result.low_cash_line),
                        width="stretch",
                        config={"displayModeBar": False},
                        key=f"{key}-chart",
                    )
                    scenario_metrics(result)
                    if st.button(copy.SAVE_PLAN, key=f"{key}-save"):
                        with st.spinner("Saving your plan…"):
                            core.save_plan(result)
                        st.session_state.pop(f"{key}-result", None)
                        st.toast(copy.ACTION_SAVED)
                        st.rerun()


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
        actions = [
            (
                a["label"],
                (
                    copy.ACTION_AFTER.format(after=money(a["impact"]["lowest_after"]))
                    if a.get("impact")
                    else a.get("detail", "")
                ),
            )
            for a in alert.actions
        ]
        info_card(copy.WHAT_YOU_CAN_DO, check_list_html(actions))
    with c3:
        outflows = [(o["label"], money(o["amount"])) for o in alert.facts.get("top_outflows", [])]
        if outflows:
            title = copy.TOP_OUTFLOWS.format(weeks=weeks(alert.weeks_ahead))
            info_card(title, rows_html(outflows), "sky")

    action_rows(alert)

    b1, b2, b3, _ = st.columns([1, 1, 1, 3])
    if b1.button(copy.SEE_WHY, key=f"why-{alert.id}", type="primary", width="stretch"):
        go_to("ask", f"Why do I have this alert: {alert.title}?")
    if b2.button(copy.TEST_WHAT_IF, key=f"whatif-{alert.id}", width="stretch"):
        go_to("whatif")
    if b3.button(copy.DISMISS, key=f"dismiss-{alert.id}", width="stretch"):
        core.dismiss_alert(alert.id)
        st.rerun()
    banner(copy.ALERT_FOOTER)
