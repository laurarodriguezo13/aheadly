"""Alerts (storyboard frame 4: early warning). Layout follows alert_detail_mockup.png."""

import html
from datetime import date

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.components import (
    action_rows,
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


def still_short_note() -> bool:
    short = core.still_short()
    if short:
        st.warning(copy.STILL_SHORT.format(gap=money(short)))
    return bool(short)


def day(d) -> str:
    """Dec 11 (the alert's own dates have no year either)."""
    return f"{d:%b} {d.day}"


def _verdict_text(result: dict) -> str:
    g = result["gap"]
    if result["verdict"] == "none":
        return copy.FIN_NONE
    if result["verdict"] == "structural":
        if result["normal_week"] <= 0:
            return copy.FIN_STRUCTURAL_LOSS.format(
                weekly=money(-result["normal_week"]), weeks=result["weeks"]
            )
        return copy.FIN_STRUCTURAL_STUCK.format(weeks=result["weeks"])
    if g["base_dips"]:
        return copy.FIN_TIMING_BASE.format(
            short=money(g["base"]),
            start=day(g["start"]),
            recovery=day(g["recovery"]),
            need=money(result["need"]),
        )
    return copy.FIN_TIMING_WORST.format(
        short=money(g["worst"]), start=day(g["start"]), need=money(result["need"])
    )


def _option_status(plan: dict, need: int) -> str:
    impact = plan.get("impact", {})
    if plan["feasible"] and impact.get("covers"):
        return copy.FIN_OK.format(after=money(impact["lowest_after"]))
    if plan["feasible"]:
        return copy.FIN_REASONS["short"].format(after=money(impact.get("lowest_after", 0)))
    return copy.FIN_REASONS[plan["reason"]].format(need=money(need))


def _option_form() -> None:
    kinds = {v["label"]: k for k, v in core.financing_kinds().items()}
    picked = st.selectbox(copy.FIN_KIND, list(kinds), key="fin-kind")
    kind = kinds[picked]
    fields = core.financing_kinds()[kind]["fields"]
    payments = core.financing_payments()
    with st.form("fin-add", clear_on_submit=True):
        raw = {"kind": kind}
        if kind in ("credit_line", "card", "loan"):
            raw["name"] = st.text_input(copy.FIN_FIELDS["name"])
        for f in fields:
            if f == "payment":
                choices = payments["out"] if kind == "supplier_terms" else payments["in"]
                raw[f] = st.selectbox(copy.FIN_FIELDS[f], choices)
            elif f in ("arrive_days", "extra_days"):
                raw[f] = st.number_input(copy.FIN_FIELDS[f], min_value=0, step=1, value=0)
            elif f in ("rate", "fee_pct"):
                raw[f] = st.number_input(copy.FIN_FIELDS[f], min_value=0.0, step=0.5, value=0.0)
            else:
                raw[f] = st.number_input(copy.FIN_FIELDS[f], min_value=0.0, step=100.0, value=0.0)
        if st.form_submit_button(copy.FIN_SAVE):
            try:
                core.add_financing_option(raw)
            except ValueError as err:
                st.error(str(err))
            else:
                st.toast(copy.FIN_ADDED)
                st.rerun()


def financing_section(expanded: bool) -> None:
    """Roadmap 3.6: timing or structural, then the owner's own options compared by cost."""
    with st.expander(copy.FIN_TITLE, expanded=expanded):
        with st.spinner(copy.FIN_WORKING):
            result = core.compare_financing()
        st.markdown(_verdict_text(result))
        st.caption(copy.FIN_NOTE)
        if result["verdict"] != "timing":
            return
        hint = result["hint"]
        if hint:
            st.info(copy.FIN_HINT.format(times=hint["times"], biggest=money(hint["biggest"])))
        if not result["options"]:
            st.markdown(copy.FIN_NO_OPTIONS)
        elif result["actions"]:
            action_rows(core, result["actions"], "fin", title=copy.FIN_BEST)
        else:
            st.warning(copy.FIN_NONE_COVER)
        options = core.financing_options()
        if result["options"]:
            st.markdown(f"**{copy.FIN_ALL}**")
            st.markdown(
                "\n".join(
                    "- "
                    + copy.FIN_ROW.format(
                        label=p["label"],
                        amount=money(p["amount"]),
                        take=day(p["take"]),
                        repay=day(p["repay"]),
                        cost=money(p["cost"]),
                        rate=f"{p['yearly_rate']:g}",
                        status=_option_status(p, result["need"]),
                    )
                    for p in result["options"]
                    if p.get("take")
                )
            )
        if options:
            st.markdown(f"**{copy.FIN_YOURS}**")
            for i, option in enumerate(options):
                c1, c2 = st.columns([5, 1])
                c1.write(core.financing_label(option))
                if c2.button(copy.FIN_REMOVE, key=f"fin-remove-{i}"):
                    core.remove_financing_option(i)
                    st.rerun()
        st.markdown(f"**{copy.FIN_ADD}**")
        _option_form()


if not alerts:
    fixes = core.suggested_fixes()
    if fixes:  # "watch": no alert, but the worst case dips below the line (roadmap 3.3)
        st.info(copy.WATCH_FIXES)
        action_rows(core, fixes, "watch")
        financing_section(expanded=False)
    else:
        st.success(copy.NO_ALERTS)

financing_shown = False
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

    action_rows(core, alert.actions, f"action-{alert.id}")
    if alert.type == "shortfall" and not financing_shown:
        financing_section(expanded=still_short_note())
        financing_shown = True

    with st.container(horizontal=True):  # each button as wide as its words
        if st.button(copy.SEE_WHY, key=f"why-{alert.id}", type="primary"):
            go_to("ask", f"Why do I have this alert: {alert.title}?")
        if st.button(copy.TEST_WHAT_IF, key=f"whatif-{alert.id}"):
            go_to("whatif")
        if st.button(copy.DISMISS, key=f"dismiss-{alert.id}"):
            core.dismiss_alert(alert.id)
            st.rerun()
    banner(copy.ALERT_FOOTER)
