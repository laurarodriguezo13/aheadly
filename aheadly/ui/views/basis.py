"""How we built your forecast (roadmap 2.6): everything the forecast counts on, each piece editable,
and what each change does to the lowest balance."""

from datetime import timedelta

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, start_page
from aheadly.ui.components import (
    day,
    money,
    proposal_card,
    rows_html,
    seasons_editor,
    section_title,
    statement_notice,
)

core = start_page(copy.BASIS_TITLE)
require_data(core)
with st.spinner("Checking your money…"):
    core.ensure_fresh()
st.caption(copy.BASIS_INTRO)
statement_notice(
    core.statement_end(),
    core.today,
    core.statement_lag_days(),
    core.status().business.name if core.example() else None,
)
basis = core.forecast_basis()


def _done(what: str, effect: dict | None = None) -> None:
    """Show what the change did on the next run (after st.rerun)."""
    st.session_state["basis_effect"] = (what, effect)
    st.rerun()


effect = st.session_state.pop("basis_effect", None)
if effect:
    what, change = effect
    if change and change["before"] is not None:
        message = copy.BASIS_EFFECT.format(
            what=what, before=money(change["before"]), after=money(change["after"])
        )
        if change["risk_before"] != change["risk_after"]:
            message += copy.BASIS_RISK_CHANGED.format(
                before=copy.RISK_NAMES.get(change["risk_before"], change["risk_before"]),
                after=copy.RISK_NAMES.get(change["risk_after"], change["risk_after"]),
            )
        st.success(message)
    else:
        st.success(what)

# ---------------------------------------------------------------- where it starts
start = basis["start"]
with st.container(border=True):
    section_title(copy.BASIS_START)
    rows = copy.BASIS_START_ROWS
    history = (
        f"{day(start['history_from'])} to {day(start['statement_end'])}" if start["history_from"] else "—"
    )
    st.markdown(
        rows_html(
            [
                (rows["balance"], money(start["balance"])),
                (rows["statement"], day(start["statement_end"]) if start["statement_end"] else "—"),
                (rows["history"], history),
                (rows["lines"], f"{start['transactions']:,}"),
                (rows["accounts"], str(start["accounts"])),
            ]
        ),
        unsafe_allow_html=True,
    )
    if start["unidentified"]:
        st.caption(copy.BASIS_UNIDENTIFIED.format(n=start["unidentified"]))

# ---------------------------------------------------------------- the normal rhythm
rhythm = basis["rhythm"]
if rhythm:
    with st.container(border=True):
        section_title(copy.BASIS_RHYTHM)
        st.markdown(
            copy.BASIS_RHYTHM_BODY.format(
                in_low=money(rhythm["in_low"]),
                in_high=money(rhythm["in_high"]),
                out_low=money(rhythm["out_low"]),
                out_high=money(rhythm["out_high"]),
                weeks=rhythm["weeks"],
                busiest=rhythm["busiest_day"],
                slowest=rhythm["slowest_day"],
            )
        )

# ---------------------------------------------------------------- busy and slow months (2.7)
info = core.seasons()
with st.container(border=True):
    section_title(copy.SEASONS_TITLE)
    if info["months"]:
        st.markdown(
            "\n".join(
                "- "
                + copy.SEASONS_USED.format(
                    month=m["name"], kind=m["kind"], pct=f"{m['used']:+.0%}" if m["used"] else "no change"
                )
                for m in info["months"]
            )
        )
    else:
        st.caption(copy.SEASONS_NONE)
    st.caption(copy.SEASON_HOW)
    with st.expander(copy.SEASONS_CHANGE):
        busy, slow, changes = seasons_editor(
            core,
            "basis-seasons",
            [m["month"] for m in info["months"] if m["kind"] == "busy"],
            [m["month"] for m in info["months"] if m["kind"] == "slow"],
            {m["month"]: m["owners"] for m in info["months"] if m["owners"] is not None},
        )
        if st.button(copy.SAVE_ANSWER, key="basis-seasons-save"):
            before = core.get_dashboard().forecast
            core.set_seasons(busy, slow, changes)
            after = core.get_dashboard().forecast
            _done(
                copy.SEASONS_SAVED,
                {
                    "before": round(before.lowest_with_today()[0]),
                    "after": round(after.lowest_with_today()[0]),
                    "risk_before": before.risk_level(core.status().business.low_cash_line),
                    "risk_after": after.risk_level(core.status().business.low_cash_line),
                },
            )

# ---------------------------------------------------------------- suggestions from a newer statement
for suggestion in basis["suggestions"]:
    with st.container(border=True):
        st.markdown(
            copy.BASIS_SUGGESTION.format(
                label=suggestion["label"],
                found=money(abs(suggestion["found"])),
                planned=money(abs(suggestion["planned"])),
            )
        )
        if st.button(
            copy.BASIS_USE_FOUND.format(found=money(abs(suggestion["found"]))), key=f"use-{suggestion['id']}"
        ):
            _done(
                copy.BASIS_SAVED.format(label=suggestion["label"]),
                core.update_plan_item(suggestion["id"], amount=abs(suggestion["found"])),
            )


def _note(row: dict) -> str:
    notes = []
    if row["paused"]:
        notes.append(copy.BASIS_PAUSED)
    if row["end_date"]:
        notes.append(copy.BASIS_ENDS.format(date=day(row["end_date"])))
    if row["maybe"]:
        notes.append(copy.BASIS_MAYBE)
    return " · ".join(notes)


def _table(rows: list[dict], repeating: bool) -> None:
    cols = copy.BASIS_COLUMNS
    st.dataframe(
        [
            {
                cols["label"]: r["label"],
                cols["amount"]: ("≈ " if r["varies"] else "") + money(r["amount"]),
                **({cols["how_often"]: r["how_often"]} if repeating else {}),
                cols["next"]: day(r["next"] if repeating else r["due"]) if (r["next"] or r["due"]) else "—",
                cols["badge"]: copy.BADGES.get(r["badge"], r["badge"]),
                cols["note"]: _note(r),
            }
            for r in rows
        ],
        hide_index=True,
        width="stretch",
    )


# ---------------------------------------------------------------- regular payments
with st.container(border=True):
    section_title(copy.BASIS_REGULAR)
    st.caption(copy.BASIS_REGULAR_HELP)
    if basis["regular"]:
        _table(basis["regular"], repeating=True)

# ---------------------------------------------------------------- one-offs, and "just say it"
with st.container(border=True):
    section_title(copy.BASIS_ONE_OFFS)
    st.caption(copy.BASIS_ONE_OFFS_HELP)
    for row in [r for r in basis["one_offs"] if r["past_due"] and not r["paused"]]:
        st.warning(
            copy.BASIS_PAST_DUE.format(label=row["label"], amount=money(row["amount"]), date=day(row["due"]))
        )
        yes, later = st.columns(2)
        if yes.button(copy.BASIS_HAPPENED, key=f"happened-{row['id']}"):
            _done(copy.BASIS_REMOVED_DONE.format(label=row["label"]), core.delete_plan_item(row["id"]))
        if later.button(copy.BASIS_NOT_YET, key=f"later-{row['id']}"):
            _done(
                copy.BASIS_SAVED.format(label=row["label"]),
                core.update_plan_item(row["id"], due_date=core.today + timedelta(days=7)),
            )
    if basis["one_offs"]:
        _table(basis["one_offs"], repeating=False)
    else:
        st.caption(copy.BASIS_NO_ONE_OFFS)
    if st.session_state.get("plan_added"):
        st.success(copy.PLAN_ITEMS_ADDED.format(n=st.session_state.pop("plan_added")))
    said = st.text_area(
        copy.JUST_SAY_IT, placeholder=copy.JUST_SAY_IT_PLACEHOLDER, help=copy.JUST_SAY_IT_HELP
    )
    if st.button(copy.READ_IT, disabled=not said.strip()):
        with st.spinner(copy.READING_IT):
            st.session_state["plan_proposals"] = core.parse_plan_text(said)
    proposals = st.session_state.get("plan_proposals")
    if proposals is not None:
        if not proposals:
            st.info(copy.NOTHING_UNDERSTOOD)
        else:
            added = proposal_card(core, proposals, "basis-plan")
            if added:
                st.session_state.pop("plan_proposals", None)
                st.session_state["plan_added"] = added
                st.rerun()

# ---------------------------------------------------------------- change a payment
everything = basis["regular"] + basis["one_offs"]
if everything:
    with st.container(border=True):
        section_title(copy.BASIS_EDIT)
        by_id = {r["id"]: r for r in everything}
        chosen = st.selectbox(
            copy.BASIS_PICK,
            list(by_id),
            format_func=lambda i: f"{by_id[i]['label']} · {money(by_id[i]['amount'])} · "
            f"{by_id[i]['how_often']}",
        )
        row = by_id[chosen]
        with st.form(f"edit-{chosen}"):
            left, right = st.columns(2)
            amount = left.number_input(
                copy.BASIS_AMOUNT, min_value=0.0, value=float(abs(row["amount"])), step=10.0
            )
            when = right.date_input(
                copy.BASIS_NEXT_DATE, value=row["next"] or row["due"], format="MM/DD/YYYY"
            )
            has_end = st.checkbox(copy.BASIS_HAS_END, value=row["end_date"] is not None)
            end = st.date_input(
                copy.BASIS_END_DATE,
                value=row["end_date"] or core.today + timedelta(days=90),
                format="MM/DD/YYYY",
            )
            if st.form_submit_button(copy.BASIS_SAVE, type="primary"):
                changes = {"end_date": end if has_end else None}
                if abs(amount - abs(row["amount"])) > 0.005:
                    changes["amount"] = amount
                if when != (row["next"] or row["due"]):
                    changes["due_date"] = when
                _done(copy.BASIS_SAVED.format(label=row["label"]), core.update_plan_item(chosen, **changes))
        buttons = st.columns(3)
        if row["paused"]:
            if buttons[0].button(copy.BASIS_RESUME, key=f"resume-{chosen}"):
                _done(copy.BASIS_RESUMED_DONE.format(label=row["label"]), core.pause_plan_item(chosen, False))
        elif buttons[0].button(copy.BASIS_PAUSE, key=f"pause-{chosen}"):
            _done(copy.BASIS_PAUSED_DONE.format(label=row["label"]), core.pause_plan_item(chosen))
        if buttons[1].button(copy.BASIS_REMOVE, key=f"remove-{chosen}"):
            _done(copy.BASIS_REMOVED_DONE.format(label=row["label"]), core.delete_plan_item(chosen))
        if row["badge"] == "statement" and buttons[2].button(copy.BASIS_LOOKS_RIGHT, key=f"confirm-{chosen}"):
            core.confirm_plan_item(chosen)
            _done(copy.BASIS_CONFIRMED)

# ---------------------------------------------------------------- left out
left_out = basis["not_counted"]
with st.container(border=True):
    section_title(copy.BASIS_NOT_COUNTED)
    lines = []
    if left_out["own_account_moves"]:
        lines.append(copy.BASIS_OWN_MOVES.format(n=left_out["own_account_moves"]))
    if left_out["card_payments"]:
        lines.append(copy.BASIS_CARD_PAYMENTS.format(n=left_out["card_payments"]))
    if left_out["some_months_only"]:
        lines.append(copy.BASIS_SOME_MONTHS.format(labels=", ".join(left_out["some_months_only"])))
    if left_out["paused"]:
        lines.append(copy.BASIS_PAUSED_LIST.format(labels=", ".join(left_out["paused"])))
    for item in left_out["switched_off"]:
        lines.append(f"{copy.BASIS_SWITCHED_OFF[item['why']]}: {item['label']} ({money(item['amount'])})")
    st.markdown("\n".join(f"- {line}" for line in lines) if lines else copy.BASIS_NOTHING_LEFT_OUT)

# ---------------------------------------------------------------- next month
month = basis["next_month"]
if month:
    with st.container(border=True):
        section_title(copy.BASIS_NEXT_MONTH.format(month=f"{month['first']:%B}"))
        names = copy.BASIS_NEXT_MONTH_ROWS
        st.markdown(
            rows_html([(names[k], money(month[k])) for k in names if month[k] or k in ("rhythm", "total")]),
            unsafe_allow_html=True,
        )
        if month["maybe_in"]:
            st.caption(copy.BASIS_MAYBE_NOTE.format(amount=money(month["maybe_in"])))
        if (month["last"] + timedelta(days=1)).month == month["last"].month:  # the forecast ends mid-month
            st.caption(copy.BASIS_PARTIAL_MONTH.format(first=day(month["first"]), last=day(month["last"])))
