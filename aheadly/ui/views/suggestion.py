"""Suggestions (roadmap R.3, a sub-tab under Ask Aheadly): every tested suggestion in one list, and
one suggestion in detail: what it is and why it helps, how to do it and the message, the owner's own
version tested again, Save as my plan, Ask about it, and "Not for me" with a reason we remember."""

from datetime import date, timedelta

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.charts import scenario_chart
from aheadly.ui.components import chart_note, impact_line, scenario_metrics, suggestion_cards

core = start_page(copy.SUGGESTIONS_TITLE)
require_data(core)


def _change_controls(adjustments: list[dict], action: dict) -> list[dict]:
    """The suggestion's own controls (roadmap R.3): a date, a percent; returns the owner's version."""
    mine = []
    for n, adjustment in enumerate(adjustments):
        kind, label = adjustment["type"], copy.CHANGE_FIELDS.get(adjustment["type"])
        key = f"change-{action.get('id')}-{n}"
        if kind == "move_item":
            picked = st.date_input(
                f"{label} ({adjustment['label']})",
                value=date.fromisoformat(adjustment["new_date"]),
                min_value=core.today + timedelta(days=1),
                format="MM/DD/YYYY",
                key=key,
            )
            mine.append({**adjustment, "new_date": picked.isoformat()})
        elif kind == "collect_early":
            due = date.fromisoformat(action["when"]) if action.get("when") else None
            picked = st.date_input(
                f"{label} ({adjustment['label']})",
                value=date.fromisoformat(adjustment["new_date"]),
                min_value=core.today,
                max_value=due - timedelta(days=1) if due else None,
                format="MM/DD/YYYY",
                key=key,
            )
            mine.append({**adjustment, "new_date": picked.isoformat()})
        elif kind == "recurring_change" and action.get("pay"):
            now = round(adjustment["amount_delta"] / action["pay"] * 100)
            pct = st.slider(label, 5, 100, min(100, max(5, now)), step=5, key=key)
            mine.append({**adjustment, "amount_delta": round(action["pay"] * pct / 100, 2)})
        elif kind == "revenue_change":
            pct = st.slider(label, 1, 20, int(adjustment["percent"]), key=key)
            mine.append({**adjustment, "percent": pct})
        else:
            mine.append(adjustment)
    return mine


def detail(opened: dict) -> None:
    action, context = opened["action"], opened["context"]
    if st.button(f"← {copy.SUGGESTION_BACK}", key="suggestion-back"):
        st.session_state.pop("open_suggestion", None)
        st.session_state.pop("suggestion_mine", None)
        st.rerun()
    st.subheader(action["label"])
    st.caption(
        (copy.SUGGESTION_FROM_SURPRISE if context else copy.SUGGESTION_FROM).format(source=opened["source"])
    )
    if action.get("detail"):
        st.markdown(action["detail"])
    st.markdown(f"**{copy.SUGGESTION_AS_IS}:** {impact_line(action['impact'])}")

    with st.expander(copy.ACTION_HOW, expanded=True):
        st.markdown("\n".join(f"{n}. {step}" for n, step in enumerate(action.get("how_to", []), 1)))
        if action.get("kind") in ("move_payment", "collect_early"):
            mine = st.session_state.get("suggestion_mine")
            if st.button(copy.ACTION_DRAFT, key="suggestion-draft"):
                version = {**action, "adjustments": mine["adjustments"]} if mine else action
                st.session_state["suggestion_message"] = core.draft_message(version)
            if st.session_state.get("suggestion_message"):
                st.code(st.session_state["suggestion_message"], language=None, wrap_lines=True)
                st.caption(copy.ACTION_DRAFT_NOTE)

    with st.container(border=True):
        st.markdown(f"**{copy.SUGGESTION_CHANGE}**")
        changeable = any(a["type"] in copy.CHANGE_FIELDS for a in action["adjustments"])
        if changeable:
            st.caption(copy.SUGGESTION_CHANGE_NOTE)
            mine_adjustments = _change_controls(action["adjustments"], action)
            if st.button(copy.SUGGESTION_TEST_MINE, key="suggestion-test", type="primary"):
                with st.spinner(copy.SUGGESTION_TESTING):
                    st.session_state["suggestion_mine"] = {
                        "adjustments": mine_adjustments,
                        **core.test_suggestion(mine_adjustments, context),
                    }
        else:
            st.caption(copy.SUGGESTION_NOTHING_TO_CHANGE)

    mine = st.session_state.get("suggestion_mine")
    if mine is None:
        with st.spinner(copy.SUGGESTION_TESTING):
            shown = core.test_suggestion(action["adjustments"], context)
    else:
        shown = mine
        st.markdown(f"**{copy.SUGGESTION_MINE}:** {impact_line(mine['impact'])}")
    result = shown["result"]
    st.plotly_chart(
        scenario_chart(result.baseline, result.scenario, result.low_cash_line),
        width="stretch",
        config={"displayModeBar": False},
        key="suggestion-chart",
    )
    chart_note(core.scenario_chart_summary(result, what="surprise" if context else "change"))
    scenario_metrics(result)

    with st.container(horizontal=True):
        save_label = copy.SUGGESTION_SAVE_MINE if mine else copy.SUGGESTION_SAVE
        if st.button(save_label, key="suggestion-save", type="primary"):
            adjustments = mine["adjustments"] if mine else action["adjustments"]
            with st.spinner(copy.SAVING_PLAN):
                core.save_suggestion(adjustments, action["label"])
            st.session_state.pop("open_suggestion", None)
            st.session_state.pop("suggestion_mine", None)
            st.toast(copy.SUGGESTION_SAVED)
            st.rerun()
        if st.button(copy.SUGGESTION_ASK, key="suggestion-ask"):
            go_to("ask", copy.SUGGESTION_ASK_QUESTION.format(label=action["label"]))

    with st.expander(copy.NOT_FOR_ME):
        reasons = copy.DECLINE_BY_KIND.get(action.get("kind"), ("already_done", "other"))
        reason = st.radio(
            copy.NOT_FOR_ME_WHY, reasons, format_func=lambda r: copy.DECLINE_LABELS[r], key="decline-reason"
        )
        note = st.text_input(copy.DECLINE_NOTE, key="decline-note")
        if st.button(copy.DECLINE_SAVE, key="decline-save"):
            with st.spinner(copy.SUGGESTION_TESTING):
                core.decline_suggestion(action, reason, note)
            st.session_state.pop("open_suggestion", None)
            st.session_state.pop("suggestion_mine", None)
            st.toast(copy.DECLINED_TOAST)
            st.rerun()


def listing() -> None:
    st.caption(copy.SUGGESTIONS_INTRO)
    with st.spinner(copy.SUGGESTIONS_WORKING):
        found = core.all_suggestions()
    if not found:
        st.success(copy.SUGGESTIONS_NONE)
    sources: dict[str, list[dict]] = {}
    for entry in found:
        sources.setdefault(entry["source"], []).append(entry)
    for n, (source, entries) in enumerate(sources.items()):
        context = entries[0]["context"]
        title = copy.SUGGESTION_FROM_SURPRISE.format(source=source) if context else source
        suggestion_cards([e["action"] for e in entries], f"all-{n}", source, title=title, context=context)
    declined = core.declined_suggestions()
    if declined:
        with st.expander(copy.DECLINED_TITLE.format(n=len(declined))):
            st.markdown(
                "\n".join(
                    "- "
                    + copy.DECLINED_ROW.format(what=r["what"], reason=copy.DECLINE_LABELS[r["reason"]])
                    + (f" ({r['note']})" if r.get("note") else "")
                    for r in declined
                )
            )
            if st.button(copy.BRING_BACK_SUGGESTIONS, key="bring-back-suggestions"):
                with st.spinner(copy.SUGGESTIONS_WORKING):
                    core.bring_back_suggestions()
                st.rerun()


opened = st.session_state.get("open_suggestion")
if opened:
    detail(opened)
else:
    listing()
