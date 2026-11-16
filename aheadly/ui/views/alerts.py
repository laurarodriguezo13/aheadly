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
    dismissed_words,
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

    action_rows(core, alert.actions, f"action-{alert.id}")
    if alert.type in ("shortfall", "watch") and not financing_shown:
        financing_section(expanded=still_short_note())
        financing_shown = True
if alerts:
    banner(copy.ALERT_FOOTER)
