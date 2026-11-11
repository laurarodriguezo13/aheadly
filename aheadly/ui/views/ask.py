"""Ask Aheadly (storyboard frame 5: ask in plain words). Features 3 and 4."""

import streamlit as st

from aheadly.ui import copy
from aheadly.ui.bootstrap import require_data, start_page
from aheadly.ui.charts import scenario_chart
from aheadly.ui.components import scenario_metrics

core = start_page(copy.CHAT_TITLE)
require_data(core)
st.caption(copy.CHAT_INTRO)
st.write("")

# Scenario cards are kept per message index only for this session (the DB keeps the text).
st.session_state.setdefault("scenario_cards", {})

biggest = core.biggest_upcoming_payment()
what_if = (
    copy.MOVE_PAYMENT_QUESTION.format(name=biggest[:1].lower() + biggest[1:])
    if biggest
    else copy.SPEND_QUESTION
)
suggestions = [*copy.CHAT_SUGGESTIONS, what_if]
chips = st.columns(len(suggestions))
for col, suggestion in zip(chips, suggestions):
    if col.button(suggestion, width="stretch"):
        st.session_state["pending_question"] = suggestion

history = core.chat_history()
for index, message in enumerate(history):
    avatar = "assets/logo_mark_transparent.png" if message["role"] == "assistant" else None
    with st.chat_message(message["role"], avatar=avatar):
        st.write(message["content"])
        result = st.session_state["scenario_cards"].get(index)
        if result is not None:
            st.plotly_chart(
                scenario_chart(result.baseline, result.scenario, result.low_cash_line),
                width="stretch",
                config={"displayModeBar": False},
            )
            scenario_metrics(result)
            if st.button(copy.SAVE_PLAN, key=f"save-{index}", type="primary"):
                with st.spinner("Saving your plan…"):
                    core.save_plan(result)
                st.success(copy.PLAN_SAVED)

question = st.chat_input(copy.CHAT_INPUT) or st.session_state.pop("pending_question", None)
if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant", avatar="assets/logo_mark_transparent.png"):
        with st.spinner(copy.CHAT_THINKING):
            answer = core.ask(question)
        if answer.used_fallback:
            st.caption(copy.FALLBACK_NOTE)
    if answer.scenario is not None:
        st.session_state["scenario_cards"][len(history) + 1] = answer.scenario
    st.rerun()

if history and st.button(copy.CLEAR_CHAT):
    core.clear_chat()
    st.session_state["scenario_cards"] = {}
    st.rerun()
