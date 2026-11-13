"""Onboarding questions (roadmap 2.7): only what the statement can't tell us, one at a time, each
saying why it matters, all skippable; answers are kept, so the owner can stop and come back."""

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import go_to, require_data, start_page
from aheadly.ui.components import proposal_card, seasons_editor

core = start_page(copy.QUESTIONS_TITLE)
require_data(core)
st.caption(copy.QUESTIONS_INTRO)
example = core.example_answers()

for note in st.session_state.pop("question_notes", []):
    st.success(note)

with st.spinner(copy.QUESTIONS_WORKING):
    state = core.onboarding()
questions, done, total = state["questions"], state["done"], state["total"]
st.progress(done / total if total else 1.0, text=copy.QUESTIONS_PROGRESS.format(done=done, total=total))

if not questions:
    st.success(copy.QUESTIONS_DONE)
    left, right = st.columns(2)
    if left.button(copy.NAV["dashboard"], type="primary"):
        go_to("dashboard")
    if right.button(copy.BASIS_LINK):
        go_to("basis")
    st.stop()

if example:
    st.info(copy.QUESTIONS_EXAMPLE)


def _next(note: str | None = None) -> None:
    if note:
        st.session_state.setdefault("question_notes", []).append(note)
    st.rerun()


question = questions[0]
with st.container(border=True):
    st.subheader(question.title)
    if question.detail:
        st.markdown(question.detail)
    st.caption(copy.WHY_LABEL + question.why)

    if question.kind == "business":
        kind = st.text_input(
            copy.BUSINESS_TYPE,
            value=example.get("business_type", ""),
            placeholder=copy.BUSINESS_TYPE_PLACEHOLDER,
        )
        pay = st.text_area(
            copy.CUSTOMERS_PAY,
            value=example.get("customers_pay", ""),
            placeholder=copy.CUSTOMERS_PAY_PLACEHOLDER,
        )
        save, skip = st.columns(2)
        if save.button(copy.SAVE_ANSWER, type="primary"):
            if kind.strip() or pay.strip():
                core.answer_business(kind, pay)
                _next()
            else:
                st.warning(copy.ANSWER_FIRST)

    elif question.kind == "seasons":
        busy, slow, changes = seasons_editor(
            core, "questions-seasons", example.get("busy_months", []), example.get("slow_months", []), {}
        )
        save, skip = st.columns(2)
        if save.button(copy.SAVE_ANSWER, type="primary"):
            with st.spinner(copy.CHAT_THINKING):
                core.answer_seasons(busy, slow, changes)
            _next(copy.SEASONS_SAVED if busy or slow else None)

    elif question.kind == "owner_pay":
        yes, no, skip = st.columns(3)
        if yes.button(copy.OWNER_PAY_YES, type="primary"):
            core.answer_owner_pay(question.payee, True)
            _next(copy.MYSTERY_SAVED.format(payee=question.payee, category=copy.CATEGORY_NAMES["owner_pay"]))
        if no.button(copy.OWNER_PAY_NO):
            core.answer_owner_pay(question.payee, False)
            _next()

    elif question.kind == "mystery":
        if question.suggestion:
            st.markdown(
                copy.MYSTERY_GUESS.format(
                    category=copy.CATEGORY_NAMES.get(question.suggestion, question.suggestion),
                    reason=question.reason,
                )
            )
        choices = [None] + core.answer_categories()
        words = example.get("mystery", {}).get(question.payee, "")
        picked = st.selectbox(
            copy.MYSTERY_PICK,
            choices,
            index=choices.index(question.suggestion) if question.suggestion in choices else 0,
            format_func=lambda c: copy.MYSTERY_NOT_SURE if c is None else copy.CATEGORY_NAMES.get(c, c),
        )
        said = st.text_input(copy.MYSTERY_WORDS, value=words, placeholder=copy.MYSTERY_WORDS_PLACEHOLDER)
        save, skip = st.columns(2)
        if save.button(copy.SAVE_ANSWER, type="primary"):
            if not (picked or said.strip()):
                st.warning(copy.ANSWER_FIRST)  # no st.stop(): the Skip button below must still show
            else:
                category = core.answer_mystery(question.payee, picked, said)
                _next(
                    copy.MYSTERY_SAVED.format(
                        payee=question.payee, category=copy.CATEGORY_NAMES.get(category, category)
                    )
                )

    else:  # coming_up: "just say it", the same as on How we built it
        if st.session_state.get("plan_added"):
            st.success(copy.PLAN_ITEMS_ADDED.format(n=st.session_state.pop("plan_added")))
        said = st.text_area(
            copy.JUST_SAY_IT, placeholder=copy.JUST_SAY_IT_PLACEHOLDER, help=copy.JUST_SAY_IT_HELP
        )
        if st.button(copy.READ_IT):  # never disabled: see basis.py
            if not said.strip():
                st.warning(copy.WRITE_FIRST)
            else:
                with st.spinner(copy.READING_IT):
                    st.session_state["plan_proposals"] = core.parse_plan_text(said)
        proposals = st.session_state.get("plan_proposals")
        if proposals is not None:
            if not proposals:
                st.info(copy.NOTHING_UNDERSTOOD)
            else:
                added = proposal_card(core, proposals, "questions-plan")
                if added:
                    st.session_state.pop("plan_proposals", None)
                    st.session_state["plan_added"] = added
                    st.rerun()
        if st.button(copy.NOTHING_ELSE, type="primary"):
            st.session_state.pop("plan_proposals", None)
            core.skip_question(question.id)
            _next()

    if question.kind != "coming_up" and skip.button(copy.SKIP, key=f"skip-{question.id}"):
        core.skip_question(question.id)
        _next()
