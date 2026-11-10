"""The owner always gets an answer: when the LLM provider is down, the chat degrades to the
offline planner (StubClient) plus templates, and the What-if explanation falls back the same way."""

from aheadly.ai.llm_client import LLMError, LLMReply, ToolCall


class DownClient:
    name = "down"

    def chat(self, messages, tools=None):
        raise LLMError("429 quota exceeded")


def test_chat_degrades_to_template_when_provider_is_down(connected_core):
    connected_core.translator._llm = DownClient()
    answer = connected_core.ask("How am I doing this month?")
    assert answer.used_fallback
    assert answer.tool_names == ["get_cash_summary"]
    assert "$8,200" in answer.text


def test_what_if_still_renders_a_scenario_card_when_provider_is_down(connected_core):
    connected_core.translator._llm = DownClient()
    answer = connected_core.ask("What if I buy the new oven next month instead?")
    assert answer.used_fallback and answer.scenario is not None
    assert "lowest balance" in answer.text


def test_alert_text_falls_back_to_template(connected_core):
    connected_core.translator._llm = DownClient()
    summary = connected_core.run_daily_check(force=True)
    alerts = connected_core.get_alerts()
    assert alerts and alerts[0].title and alerts[0].body
    assert summary.alerts_raised + summary.alerts_updated >= 0


class HalfBrokenClient:
    """Calls a tool with bad arguments, then dies: the fallback must not trust the error payload."""

    name = "half-broken"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            bad = {"name": "bad", "adjustments": [{"type": "one_time_expense"}]}
            return LLMReply(tool_calls=[ToolCall("x1", "run_scenario", bad)])
        raise LLMError("503")


def test_fallback_ignores_failed_tool_results(connected_core):
    connected_core.translator._llm = HalfBrokenClient()
    answer = connected_core.ask("How am I doing this month?")
    assert answer.used_fallback and "$8,200" in answer.text
    assert answer.tool_names == ["run_scenario", "get_cash_summary"]
