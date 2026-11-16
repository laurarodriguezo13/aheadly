"""Financing (roadmap 3.6; its own sub-tab under Ask Aheadly since R.2, always there, not only with
an alert): is a gap about timing or about the business losing money, the owner's own options compared
by cost, and a loan the owner is thinking about tested on their numbers. No lender is named, nothing
is offered, and the not-advice note stays."""

from datetime import timedelta

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, start_page
from aheadly.ui.charts import scenario_chart
from aheadly.ui.components import action_rows, chart_note, money, scenario_metrics

core = start_page(copy.FINANCING_TITLE)
require_data(core)
st.caption(copy.FINANCING_INTRO)


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


def financing_section() -> None:
    """Roadmap 3.6: timing or structural, then the owner's own options compared by cost."""
    with st.container(border=True):
        st.markdown(f"**{copy.FIN_TITLE}**")
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


def loan_section() -> None:
    with st.container(border=True):
        st.markdown(f"**{copy.LOAN_TITLE}**")
        st.caption(copy.LOAN_INTRO)
        with st.form("loan"):
            c1, c2, c3 = st.columns(3)
            amount = c1.number_input(copy.LOAN_FIELDS["amount"], min_value=100.0, value=5000.0, step=500.0)
            rate = c2.number_input(
                copy.LOAN_FIELDS["rate"], min_value=0.0, max_value=100.0, value=18.0, step=0.5
            )
            months = c3.number_input(copy.LOAN_FIELDS["months"], min_value=1, max_value=120, value=6, step=1)
            c4, c5 = st.columns(2)
            fees = c4.number_input(copy.LOAN_FIELDS["fees"], min_value=0.0, value=0.0, step=25.0)
            start = c5.date_input(
                copy.LOAN_FIELDS["start"],
                value=core.today + timedelta(days=1),
                min_value=core.today,
                format="MM/DD/YYYY",
            )
            run = st.form_submit_button(copy.LOAN_RUN, type="primary")
        if run:
            with st.spinner(copy.LOAN_WORKING):
                try:
                    st.session_state["loan_test"] = core.test_loan(amount, rate, int(months), fees, start)
                except ValueError as err:
                    st.error(str(err))
        loan = st.session_state.get("loan_test")
        if loan is None:
            return
        last = loan["last_payment"]
        st.markdown(
            (copy.LOAN_RESULT if loan["total_cost"] != loan["interest"] else copy.LOAN_RESULT_NO_FEES).format(
                monthly=money(loan["monthly_payment"]),
                months=loan["payments"],
                last=f"{last:%b} {last.day}, {last.year}",
                interest=money(loan["interest"]),
                cost=money(loan["total_cost"]),
            )
        )
        if loan["payments_in_window"] == 1:
            st.caption(copy.LOAN_WINDOW_ONE.format(paid=money(loan["paid_in_window"])))
        elif loan["payments_in_window"]:
            st.caption(
                copy.LOAN_WINDOW.format(n=loan["payments_in_window"], paid=money(loan["paid_in_window"]))
            )
        else:
            st.caption(copy.LOAN_WINDOW_NONE)
        result = loan["result"]
        st.plotly_chart(
            scenario_chart(result.baseline, result.scenario, result.low_cash_line),
            width="stretch",
            config={"displayModeBar": False},
            key="loan-chart",
        )
        chart_note(core.scenario_chart_summary(result))
        scenario_metrics(result)
        st.caption(copy.FIN_NOTE)
        if st.button(copy.SAVE_PLAN, key="loan-save"):
            with st.spinner(copy.SAVING_PLAN):
                core.save_plan(result)
            st.session_state.pop("loan_test", None)
            st.success(copy.PLAN_SAVED)


short = core.still_short()
if short:
    st.warning(copy.STILL_SHORT.format(gap=money(short)))
financing_section()
loan_section()
