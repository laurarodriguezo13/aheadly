"""LLM API adapters (component "Generate Text").

Three clients share one `chat(messages, tools)` interface (polymorphism):
  * StubClient      offline, rule-based; the default without a key, the fallback, and the tests
  * GeminiClient    the course default, via Google's OpenAI-compatible endpoint
  * AnthropicClient Claude via the official anthropic SDK

Messages use one neutral format (OpenAI-style dicts):
  {"role": "system"|"user"|"assistant", "content": str}
  {"role": "assistant", "content": str|None, "tool_calls": [ToolCall...]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}
Tools use one neutral format: {"name", "description", "parameters": <json schema>}.
"""

from __future__ import annotations

import json
import logging
import time
import re
import uuid
from typing import Any
from dataclasses import dataclass, field
from datetime import date

from aheadly.ai.plan_text import amounts_in, dates_in, read_by_rules
from aheadly.ai.templates import alert_text, answer_from_tool, chart_summary, insight_body, message_text
from aheadly.domain import end_of_next_month
from aheadly.config import Settings

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
RETRY_STATUSES = {429, 503}  # rate limit, high demand
MAX_RETRY_WAIT_SECONDS = 25

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    extra: dict = field(default_factory=dict)  # provider passthrough (Gemini 3 'thought signatures')


@dataclass
class LLMReply:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMError(RuntimeError):
    """Raised when a provider call fails; the Insight Translator degrades gracefully."""


# --------------------------------------------------------------------------- Gemini


def _retry_after_seconds(detail: Any, default: float = 4.0) -> float:
    """How long Google asks us to wait: RetryInfo 'retryDelay': '17s' (or '10766s' for a daily quota)."""
    text = str(detail)
    match = re.search(r"retryDelay': '(\d+)s", text) or re.search(r"retry in ([\d.]+)s", text)
    if match:
        return float(match.group(1)) + 1
    if re.search(r"retry in \d+h", text):  # daily quota: hours away, do not wait
        return float("inf")
    return default


class GeminiClient:
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI  # lecture 12: Gemini speaks the OpenAI chat format

        self._client = OpenAI(api_key=api_key, base_url=GEMINI_OPENAI_BASE_URL, max_retries=0)
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMReply:
        import openai

        request = dict(
            model=self.model,
            messages=[self._to_wire(m) for m in messages],
            tools=[{"type": "function", "function": t} for t in tools] if tools else openai.NOT_GIVEN,
            temperature=0.2,
        )
        for attempt in (1, 2, 3):  # free-tier quotas are per minute: wait as long as Google asks, then retry
            try:
                response = self._client.chat.completions.create(**request)
                break
            except openai.APIStatusError as exc:
                detail = exc.body or str(exc)  # the SDK's str() hides Google's message
                wait = _retry_after_seconds(detail)
                if exc.status_code in RETRY_STATUSES and attempt < 3 and wait <= MAX_RETRY_WAIT_SECONDS:
                    logger.warning(
                        "Gemini returned %s; retrying in %ss (attempt %s)", exc.status_code, wait, attempt
                    )
                    time.sleep(wait)
                    continue
                raise LLMError(f"Gemini call failed ({self.model}): {detail}") from exc
            except openai.APIError as exc:  # connection problems and the like
                raise LLMError(f"Gemini call failed ({self.model}): {exc}") from exc
        choice = response.choices[0].message
        calls = [
            ToolCall(
                tc.id,
                tc.function.name,
                json.loads(tc.function.arguments or "{}"),
                extra=(tc.model_extra or {}).get("extra_content") or {},
            )
            for tc in (choice.tool_calls or [])
        ]
        return LLMReply(content=choice.content, tool_calls=calls)

    @staticmethod
    def _to_wire(message: dict) -> dict:
        if message["role"] == "assistant" and message.get("tool_calls"):
            return {
                "role": "assistant",
                "content": message.get("content") or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        # Gemini 3 rejects a tool-call history without its thought signature
                        **({"extra_content": tc.extra} if tc.extra else {}),
                    }
                    for tc in message["tool_calls"]
                ],
            }
        return {k: v for k, v in message.items() if k in ("role", "content", "tool_call_id", "name")}


# ------------------------------------------------------------------------ Anthropic
class AnthropicClient:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMReply:
        import anthropic

        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        wire = [self._to_wire(m) for m in messages if m["role"] != "system"]
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=wire,
                tools=[
                    {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                    for t in (tools or [])
                ],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Claude call failed: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("Claude declined to answer this request")
        text = "".join(b.text for b in response.content if b.type == "text") or None
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"]
        return LLMReply(content=text, tool_calls=calls)

    @staticmethod
    def _to_wire(message: dict) -> dict:
        if message["role"] == "assistant" and message.get("tool_calls"):
            blocks = [{"type": "text", "text": message["content"]}] if message.get("content") else []
            blocks += [
                {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                for tc in message["tool_calls"]
            ]
            return {"role": "assistant", "content": blocks}
        if message["role"] == "tool":
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": message["content"],
                    }
                ],
            }
        return {"role": message["role"], "content": message["content"]}


# ----------------------------------------------------------------------------- Stub
class StubClient:
    """Deterministic offline stand-in. Picks a tool from keywords, then fills a template.

    It exercises exactly the same tool loop as the real providers, which keeps the
    app, the demo script and the tests runnable without any API key.
    """

    name = "stub"

    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMReply:
        last = messages[-1]
        if last["role"] == "tool":
            return LLMReply(content=answer_from_tool(last["name"], json.loads(last["content"])))
        if last["role"] == "user" and last["content"].startswith("DRAFT_MESSAGE"):
            facts = json.loads(last["content"][len("DRAFT_MESSAGE") :])
            return LLMReply(content=json.dumps({"message": message_text(facts)}))
        if last["role"] == "user" and last["content"].startswith("WRITE_INSIGHT"):
            facts = json.loads(last["content"][len("WRITE_INSIGHT") :])
            return LLMReply(content=json.dumps({"body": insight_body(facts)}))
        if last["role"] == "user" and last["content"].startswith("SUMMARIZE_CHART"):
            facts = json.loads(last["content"][len("SUMMARIZE_CHART") :])
            return LLMReply(content=json.dumps({"summary": chart_summary(facts)}))
        if last["role"] == "user" and last["content"].startswith("WRITE_ALERT"):
            return LLMReply(content=json.dumps(alert_text(json.loads(last["content"][len("WRITE_ALERT") :]))))
        call = self.plan(last["content"], scheduled_labels(messages))
        if isinstance(call, str):  # a question back to the owner, no tool needed
            return LLMReply(content=call)
        return LLMReply(tool_calls=[call])

    # ----- turn 1: choose a tool
    def plan(self, question: str, labels: list[str] | None = None) -> ToolCall | str:
        """Keyword routing (or a question back, as text, when a what-if is missing what it needs). Also the Insight Translator's fallback planner when a real provider is down.
        `labels` = the business's scheduled items, so "move the flour order" finds the right one."""
        q = question.lower()
        call_id = f"stub-{uuid.uuid4().hex[:8]}"
        if any(
            w in q
            for w in (
                "safe to spend",
                "safely spend",
                "can i spend",
                "afford",
                "pay myself",
                "safely pay",
                "my own pay",
                "my pay",
            )
        ):
            return ToolCall(call_id, "safe_to_spend", {})
        if any(
            w in q
            for w in ("cover this", "cover the gap", "cover it", "borrow", "loan", "financ", "credit line")
        ):
            return ToolCall(call_id, "compare_financing", {})
        if any(
            w in q
            for w in (
                "noticed",
                "notice",
                "insight",
                "stand out",
                "stands out",
                "unusual",
                "pattern",
                "anything odd",
            )
        ):
            return ToolCall(call_id, "get_insights", {})
        if "what if" in q or "instead" in q:
            args = self._scenario_args(q, labels or [])
            if isinstance(args, str):  # roadmap R.1: ask for what's missing instead of guessing
                return args
            return ToolCall(call_id, "run_scenario", args)
        proposals = self._plan_items(question)
        if proposals:
            return ToolCall(call_id, "propose_plan_items", {"items": proposals})
        if any(w in q for w in SUGGESTION_WORDS) and "alert" not in q:  # roadmap R.3b
            return ToolCall(call_id, "get_suggestions", {})
        if any(w in q for w in ("alert", "warning", "why", "fix")):
            return ToolCall(call_id, "get_alerts", {})
        if any(w in q for w in ("bill", "payment", "due", "going out", "pay")):
            return ToolCall(call_id, "get_upcoming_outflows", {"weeks": 8})
        if "next month" in q:
            return ToolCall(call_id, "get_forecast", {"until": end_of_next_month(self.today).isoformat()})
        if any(w in q for w in ("enough", "forecast", "weeks", "run out", "short")):
            return ToolCall(call_id, "get_forecast", {"weeks": 8})
        if any(w in q for w in ("transaction", "spent", "sales")):
            return ToolCall(call_id, "get_transactions", {"limit": 10})
        return ToolCall(call_id, "get_cash_summary", {})

    def _plan_items(self, question: str) -> list[dict]:
        """The owner telling us about money still to come ("I'm buying a laptop for $1,650 on Dec 2"),
        not asking a question: the offline reader's items, as the model would propose them."""
        q = question.strip().lower()
        if q.endswith("?") or q.split(" ", 1)[0] in QUESTION_WORDS:
            return []
        items = read_by_rules(question, self.today)
        return [
            {
                "label": i.label,
                "amount": i.amount,
                "direction": i.direction,
                "date": i.due_date.isoformat() if i.due_date else None,
                "repeats": i.repeats,
                "certainty": "maybe" if i.certainty == "maybe" else "sure",
            }
            for i in items
            if i.amount
        ]

    def _scenario_args(self, q: str, labels: list[str]) -> dict | str:
        """The what-if to test, or (roadmap R.1) a question back when a purchase has no amount or no
        date: guessing them tested a made-up purchase, and "a new fridge" once moved the New oven."""
        label = best_label(q, labels)
        bare = re.search(r"\$?\s?(\d[\d,]{2,})", q)
        amounts = amounts_in(q) or ([float(bare.group(1).replace(",", ""))] if bare else [])
        dates, _ = dates_in(q, self.today)
        when = dates[0] if dates else end_of_next_month(self.today) if "next month" in q else None
        buying = any(w in q for w in ("buy", "spend", "purchase", "hire", "get a new", "order a"))
        if buying and "instead" not in q and not (label and not amounts):
            if not amounts or when is None:
                return need_purchase_details(q, bool(amounts), when is not None)
            return {
                "name": "One-time expense",
                "adjustments": [
                    {
                        "type": "one_time_expense",
                        "amount": amounts[0],
                        "date": when.isoformat(),
                        "label": purchase_name(q) or "New expense",
                    }
                ],
            }
        percent = re.search(r"(\d+)\s?%", q)
        if percent and "sales" in q:
            sign = -1 if any(w in q for w in ("drop", "fall", "lose", "down")) else 1
            return {
                "name": f"Sales {sign * int(percent.group(1)):+d}%",
                "adjustments": [{"type": "revenue_change", "percent": sign * int(percent.group(1))}],
            }
        if not label:
            return WHAT_TO_TEST
        new_date = when if when and when > self.today else end_of_next_month(self.today)
        return {
            "name": f"Move {label} to {new_date:%b} {new_date.day}",
            "adjustments": [{"type": "move_item", "label": label, "new_date": new_date.isoformat()}],
        }


WHAT_TO_TEST = (
    "I can test that, but I need a bit more: which payment to move or change, or what you'd buy, "
    'how much it costs and when. For example: "What if I move the flour order to next month?"'
)


PURCHASE_RE = re.compile(
    r"\b(?:buy|purchase|get|order|hire)\s+((?:a|an|the|another|some)\s+)?([a-z][a-z ]{1,30}?)"
    r"(?=\s+(?:for|on|at|in|by|next|this|costing|that)\b|[?.,!$]|$)"
)


def purchase_name(q: str, with_article: bool = False) -> str:
    """'what if i buy a new fridge for $1,200?' → 'New fridge' (or 'a new fridge')."""
    found = PURCHASE_RE.search(q)
    if not found:
        return ""
    if with_article:
        return f"{found.group(1) or ''}{found.group(2).strip()}"
    return found.group(2).strip().capitalize()


def need_purchase_details(q: str, has_amount: bool, has_date: bool) -> str:
    thing = purchase_name(q, with_article=True) or "it"
    missing = (
        "when you'd pay for it"
        if has_amount
        else "about how much it costs" if has_date else "about how much it costs and when you'd pay for it"
    )
    # no example amounts or dates: every number in an answer must come from a tool result
    return (
        f"Happy to test buying {thing}. To do it on your numbers I need {missing}. "
        "Tell me and I'll show you how it changes your cash."
    )


SUGGESTION_WORDS = (
    "suggestion",
    "suggest",
    "what can i do",
    "what should i do",
    "what would help",
    "how much do i need",
    "how much am i short",
    "how short",
)
QUESTION_WORDS = {"what", "how", "when", "will", "can", "should", "is", "do", "does", "am", "are", "why", "which",
                  "could", "would", "qué", "que", "cuándo", "cuando", "cómo", "como", "puedo", "debo"}  # fmt: skip

# -------------------------------------------------------------------------- factory
SCHEDULED_PREFIX = "Scheduled items you can move or remove by label: "


def scheduled_labels(messages: list[dict]) -> list[str]:
    """The labels the system prompt lists, read the same way the real model reads them."""
    for message in messages:
        if message.get("role") != "system":
            continue
        for line in str(message.get("content", "")).splitlines():
            if line.startswith(SCHEDULED_PREFIX):
                text = line[len(SCHEDULED_PREFIX) :].strip().rstrip(".")
                return [] if text == "none" else [part.strip() for part in text.split(",") if part.strip()]
    return []


# words many payment names share: a question naming one of them doesn't name that payment (roadmap R.1)
GENERIC_WORDS = {"payment", "payments", "order", "orders", "bill", "bills", "monthly", "weekly", "yearly",
                 "invoice", "transfer", "purchase", "expense", "other", "pago", "pagos", "factura", "compra",
                 "pedido", "mensual"}  # fmt: skip


def best_label(question: str, labels: list[str]) -> str | None:
    """The scheduled item a question talks about: its whole name, or else most of its distinctive
    words (never "new" or "payment": "a new fridge" is not the New oven)."""
    best, best_score = None, 0
    for label in labels:
        name = label.lower()
        if name in question:
            return label
        words = {w for w in re.findall(r"[a-záéíóúñ]+", name) if len(w) > 3 and w not in GENERIC_WORDS}
        score = sum(1 for w in words if w in question)
        if score > best_score:
            best, best_score = label, score
    return best


def create_llm_client(settings: Settings):
    """Pick the provider from settings; fail fast if a real provider lacks its key."""
    settings.validate()
    if settings.llm_provider == "gemini":
        return GeminiClient(settings.gemini_api_key, settings.gemini_model)
    if settings.llm_provider == "anthropic":
        return AnthropicClient(settings.anthropic_api_key, settings.anthropic_model)
    return StubClient()
