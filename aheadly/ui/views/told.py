"""What you told us (roadmap R.3c, a sub-tab under Your business): every answer the owner gave, in
one place, each one changeable: the business, busy and slow months, their own pay, the payments
they named, notes for the chat, what never to suggest, and things we noticed they set aside."""

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.components import section_title

core = start_page(copy.TOLD_TITLE)
require_data(core)
st.caption(copy.TOLD_INTRO)

told = core.told_us()
categories = core.answer_categories()


def _done(message: str = copy.TOLD_US_SAVED) -> None:
    st.toast(message)
    st.rerun()


with st.container(border=True):
    section_title(copy.TOLD_BUSINESS)
    with st.form("told-business"):
        what = st.text_input(copy.BUSINESS_TYPE, value=told["business_type"])
        pay = st.text_area(copy.CUSTOMERS_PAY, value=told["customers_pay"])
        if st.form_submit_button(copy.TOLD_BUSINESS_SAVE):
            core.answer_business(what, pay)
            _done()

with st.container(border=True):
    section_title(copy.TOLD_SEASONS)
    months = told["seasons"]["months"]
    if months:
        st.markdown(
            "\n".join(
                f"- {m['name']} ({m['kind']}): " + (f"{m['used']:+.0%}" if m["used"] else "no change")
                for m in months
            )
        )
    else:
        st.caption(copy.TOLD_SEASONS_NONE)
    if st.button(copy.TOLD_SEASONS_CHANGE, key="told-seasons"):
        go_to("basis")

with st.container(border=True):
    section_title(copy.TOLD_OWNER_PAY)
    if not told["owner_pay"]:
        st.caption(copy.TOLD_NOTHING)
    for n, rule in enumerate(told["owner_pay"]):
        left, right = st.columns([4, 1], vertical_alignment="center")
        left.write(copy.TOLD_OWNER_PAY_ROW.format(label=rule["payee"]))
        if right.button(copy.TOLD_NOT_MY_PAY, key=f"told-pay-{n}"):
            with st.spinner(copy.SAVING_ANSWER):
                core.forget_payee_answer(rule["match_key"])
            _done()

with st.container(border=True):
    section_title(copy.TOLD_PAYEES)
    if not told["payees"]:
        st.caption(copy.TOLD_NOTHING)
    for n, rule in enumerate(told["payees"]):
        left, mid, right = st.columns([3, 2, 1], vertical_alignment="bottom")
        left.markdown(
            f"**{rule['payee']}**"
            + (f"  \n{copy.TOLD_YOU_SAID.format(said=rule['said'])}" if rule["said"] else "")
        )
        picked = mid.selectbox(
            copy.MYSTERY_PICK,
            categories,
            index=categories.index(rule["category"]) if rule["category"] in categories else 0,
            format_func=lambda c: copy.CATEGORY_NAMES.get(c, c),
            key=f"told-payee-{n}",
            label_visibility="collapsed",
        )
        if picked != rule["category"] and right.button(copy.TOLD_PAYEE_SAVE, key=f"told-payee-save-{n}"):
            with st.spinner(copy.SAVING_ANSWER):
                core.change_payee_answer(rule["match_key"], picked)
            _done()
        if picked == rule["category"] and right.button(copy.TOLD_FORGET, key=f"told-payee-forget-{n}"):
            with st.spinner(copy.SAVING_ANSWER):
                core.forget_payee_answer(rule["match_key"])
            _done()

with st.container(border=True):
    section_title(copy.TOLD_NOTES)
    if not told["notes"]:
        st.caption(copy.TOLD_NOTHING)
    for n, note in enumerate(told["notes"]):
        left, right = st.columns([5, 1], vertical_alignment="center")
        left.write(note["text"])
        if right.button(copy.TOLD_REMOVE, key=f"told-note-{n}"):
            core.remove_owner_note(n)
            _done()
    with st.form("told-note", clear_on_submit=True):
        new = st.text_input(copy.TOLD_NOTE_ADD)
        if st.form_submit_button(copy.TOLD_NOTE_ADD_BUTTON) and new.strip():
            core.add_owner_note(new)
            _done()

with st.container(border=True):
    section_title(copy.TOLD_LIMITS)
    if not told["limits"]:
        st.caption(copy.TOLD_NOTHING)
    for n, rule in enumerate(told["limits"]):
        left, right = st.columns([5, 1], vertical_alignment="center")
        reason = copy.DECLINE_LABELS.get(rule.get("reason"), "")
        left.write(copy.TOLD_LIMIT_ROW.format(what=rule["what"], reason=reason))
        if right.button(copy.TOLD_REMOVE, key=f"told-limit-{n}"):
            with st.spinner(copy.SUGGESTIONS_WORKING):
                core.remove_declined(n)
            _done()

if told["set_aside"]:
    with st.container(border=True):
        section_title(copy.TOLD_SET_ASIDE)
        for n, item in enumerate(told["set_aside"]):
            left, right = st.columns([5, 1], vertical_alignment="center")
            left.write(
                copy.TOLD_SET_ASIDE_ROW.format(
                    title=item["title"], reason=copy.TOLD_SET_ASIDE_REASONS.get(item["reason"], "")
                )
            )
            if right.button(copy.TOLD_BRING_BACK, key=f"told-insight-{n}"):
                core.bring_back_insight(item["type"])
                _done()
