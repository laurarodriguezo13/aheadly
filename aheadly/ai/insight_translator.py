"""Insight Translator (component "Explain Results").

The only component that talks to the LLM. Two jobs:
  A. write_alert(facts)  → plain-language title, body and actions
  B. answer(question)    → chat with function calling, including what-ifs
Every answer passes the number guardrail; on failure we retry once and then
fall back to a deterministic template. Errors never pass silently (logged),
but the owner always gets an answer: if the provider is down, the offline planner
(StubClient) picks the tool and the template writes the sentence.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from aheadly.ai import prompts, templates
from aheadly.ai.categorizer import CATEGORIES
from aheadly.ai.guardrails import check_numbers
from aheadly.ai.llm_client import LLMError, LLMReply, StubClient
from aheadly.ai.plan_text import PROPOSE_TOOL, ProposedItem, read_by_rules, read_tool_call
from aheadly.data.connectors.owner_files import KINDS as FILE_KINDS
from aheadly.data.connectors.owner_files import ROLES as FILE_ROLES
from aheadly.ai.tools import ToolDispatcher
from aheadly.domain import ChatAnswer

# categories the model may suggest (never "other", and card payments are found by the transfers rule)
SUGGESTABLE = tuple(c for c in CATEGORIES if c not in ("other", "card_payment"))

logger = logging.getLogger(__name__)

# "$-748" → "-$748" in alert text written by the model
_MINUS_AFTER_DOLLAR = re.compile(r"\$-(\d)")


@dataclass
class AlertText:
    title: str
    body: str
    actions: list[dict[str, str]]


class InsightTranslator:
    def __init__(self, llm, tools: ToolDispatcher, max_tool_rounds: int = 4):
        self._llm = llm
        self._tools = tools
        self.max_tool_rounds = max_tool_rounds
        self.guardrail_failures = 0  # simple observability counter

    @property
    def provider_name(self) -> str:
        return self._llm.name

    # ------------------------------------------------------------- job A: alert
    def write_alert(self, facts: dict) -> AlertText:
        messages = [
            {"role": "system", "content": prompts.ALERT_INSTRUCTIONS},
            {"role": "user", "content": prompts.ALERT_PROMPT.format(facts_json=json.dumps(facts))},
        ]
        try:
            reply = self._llm.chat(messages)
            parsed = json.loads(_strip_code_fence(reply.content or ""))
            # the title says how serious it is, so it follows the numbers (live check, 2026-11-12)
            body = _MINUS_AFTER_DOLLAR.sub(r"-$\1", parsed["body"])
            text = AlertText(templates.alert_title(facts), body, parsed.get("actions", [])[:3])
            if not check_numbers(f"{text.title} {text.body}", [facts]).passed:
                raise ValueError("alert used a number that is not in the facts")
            return text
        except (LLMError, ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.warning("write_alert fell back to template: %s", exc)
            self.guardrail_failures += 1
            fallback = templates.alert_text(facts)
            return AlertText(fallback["title"], fallback["body"], fallback["actions"])

    # -------------------------------------------------------------- job B: chat
    def answer(self, question: str, history: list[dict], context: dict[str, Any]) -> ChatAnswer:
        self._tools.last_scenario = None
        self._tools.last_proposals = []
        self._tools.last_question = question
        messages = [{"role": "system", "content": prompts.CHAT_SYSTEM_PROMPT.format(**context)}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history[-8:]]
        messages.append({"role": "user", "content": question})
        evidence: list[Any] = []
        tool_names: list[str] = []
        try:
            reply = self._run_tool_loop(messages, evidence, tool_names)
            text = self._verified_text(reply, messages, evidence, tool_names)
        except LLMError as exc:
            logger.error("LLM call failed, using template answer: %s", exc)
            return self._fallback(question, evidence, tool_names)
        if text is None:
            return self._fallback(question, evidence, tool_names)
        return ChatAnswer(
            text=text,
            tool_names=tool_names,
            scenario=self._tools.last_scenario,
            proposals=self._tools.last_proposals,
        )

    # ------------------------------------------------------ owner's files: what kind is it
    def classify_owner_file(self, headers: list[str]) -> tuple[str, dict[str, str]] | None:
        """Roadmap 2.5: when the column titles don't say what a file is, the model may know: the kind,
        and which title is which (role → title). It sees the titles only, never a value (an employee
        list's names and pay stay here). Titles it names must be real titles of the file."""
        if isinstance(self._llm, StubClient) or not headers:
            return None
        tool = {
            "name": "classify_owner_file",
            "description": "Say which kind of file this is and which column title holds what.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": [*FILE_KINDS, "other"]},
                    "columns": {
                        "type": "object",
                        "description": "role → the exact column title",
                        "properties": {role: {"type": "string", "enum": headers} for role in FILE_ROLES},
                    },
                },
                "required": ["kind"],
            },
        }
        messages = [
            {"role": "system", "content": prompts.FILE_KIND_INSTRUCTIONS},
            {"role": "user", "content": json.dumps({"column_titles": headers}, ensure_ascii=False)},
        ]
        try:
            reply = self._llm.chat(messages, [tool])
        except LLMError as exc:
            logger.warning("file kind: model failed: %s", exc)
            return None
        for call in reply.tool_calls:
            args = call.arguments if isinstance(call.arguments, dict) else {}
            if call.name == "classify_owner_file" and args.get("kind") in FILE_KINDS:
                given = args.get("columns") if isinstance(args.get("columns"), dict) else {}
                columns = {r: h for r, h in given.items() if r in FILE_ROLES and h in headers}
                return args["kind"], columns
        return None

    # ------------------------------------------------------ category suggestions (roadmap 2.7)
    def suggest_categories(self, payees: list[str]) -> dict[str, tuple[str, str]]:
        """The model's guess for payees the rules left in "other": payee → (category, reason). It
        sees the names only. A category not on the list, or a payee it wasn't asked about, is
        dropped; nothing is applied until the owner confirms. Offline: no suggestions."""
        if isinstance(self._llm, StubClient) or not payees:
            return {}
        tool = {
            "name": "suggest_categories",
            "description": "Suggest a category for each payee you can reasonably place.",
            "parameters": {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "payee": {"type": "string", "enum": payees},
                                "category": {"type": "string", "enum": list(SUGGESTABLE)},
                                "reason": {"type": "string"},
                            },
                            "required": ["payee", "category"],
                        },
                    }
                },
                "required": ["suggestions"],
            },
        }
        messages = [
            {"role": "system", "content": prompts.CATEGORY_SUGGESTION_INSTRUCTIONS},
            {"role": "user", "content": json.dumps({"payees": payees}, ensure_ascii=False)},
        ]
        try:
            reply = self._llm.chat(messages, [tool])
        except LLMError as exc:
            logger.warning("category suggestions: model failed: %s", exc)
            return {}
        out: dict[str, tuple[str, str]] = {}
        for call in reply.tool_calls:
            args = call.arguments if isinstance(call.arguments, dict) else {}
            if call.name != "suggest_categories" or not isinstance(args.get("suggestions"), list):
                continue
            for s in args["suggestions"]:
                if isinstance(s, dict) and s.get("payee") in payees and s.get("category") in SUGGESTABLE:
                    out[s["payee"]] = (s["category"], str(s.get("reason", ""))[:120])
        return out

    # ------------------------------------------------------ job C: just say it
    def extract_plan_items(self, text: str, today) -> tuple[list[ProposedItem], bool]:
        """Roadmap 2.4: the owner's own words → plan items to confirm. Returns (items, used_rules).
        The model reads it when one is connected; the offline rules read it otherwise or when the
        model fails or finds nothing."""
        if not isinstance(self._llm, StubClient):
            messages = [
                {"role": "system", "content": prompts.PLAN_TEXT_INSTRUCTIONS.format(today=today.isoformat())},
                {"role": "user", "content": text},
            ]
            try:
                reply = self._llm.chat(messages, [PROPOSE_TOOL])
                calls = [c for c in reply.tool_calls if c.name == PROPOSE_TOOL["name"]]
                items = [i for c in calls for i in read_tool_call(c.arguments, today, text)]
                if items:
                    return items, False
            except LLMError as exc:
                logger.warning("plan text: model failed, reading with rules: %s", exc)
        return read_by_rules(text, today), True

    def explain_scenario(self, summary: dict, context: dict[str, Any]) -> str:
        """Used by the What-if form page: explain numbers the engine already produced."""
        messages = [
            {"role": "system", "content": prompts.CHAT_SYSTEM_PROMPT.format(**context)},
            {
                "role": "user",
                "content": f"Explain this what-if result in plain words: {summary['scenario_name']}",
            },
            {"role": "assistant", "content": None, "tool_calls": []},
        ]
        messages[-1] = {
            "role": "tool",
            "tool_call_id": "form",
            "name": "run_scenario",
            "content": json.dumps(summary),
        }
        try:
            reply = self._llm.chat(messages, self._tools.schemas)
            text = self._verified_text(reply, messages, [summary], ["run_scenario"])
        except LLMError as exc:
            logger.error("explain_scenario failed: %s", exc)
            text = None
        return text or templates.answer_from_tool("run_scenario", summary)

    # ----------------------------------------------------------------- helpers
    def _run_tool_loop(self, messages: list[dict], evidence: list, tool_names: list[str]) -> LLMReply:
        reply = self._llm.chat(messages, self._tools.schemas)
        rounds = 0
        while reply.tool_calls and rounds < self.max_tool_rounds:
            messages.append({"role": "assistant", "content": reply.content, "tool_calls": reply.tool_calls})
            for call in reply.tool_calls:
                result = self._tools.dispatch(call.name, call.arguments)
                evidence.append(result)
                tool_names.append(call.name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": json.dumps(result),
                    }
                )
            reply = self._llm.chat(messages, self._tools.schemas)
            rounds += 1
        return reply

    def _verified_text(
        self, reply: LLMReply, messages: list[dict], evidence: list, tool_names: list[str]
    ) -> str | None:
        text = reply.content or ""
        check = check_numbers(text, evidence)
        if check.passed and text:
            return text
        self.guardrail_failures += 1
        logger.warning("guardrail rejected numbers %s; retrying once", check.unverified)
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": prompts.GUARDRAIL_RETRY.format(numbers=check.unverified)})
        retry = self._llm.chat(messages, self._tools.schemas)
        if retry.tool_calls:  # the model asked for data instead of guessing: run one more round
            retry = self._run_tool_loop_from(retry, messages, evidence, tool_names)
        retry_text = retry.content or ""
        return retry_text if retry_text and check_numbers(retry_text, evidence).passed else None

    def _run_tool_loop_from(
        self, reply: LLMReply, messages: list[dict], evidence: list, tool_names: list[str]
    ) -> LLMReply:
        messages.append({"role": "assistant", "content": reply.content, "tool_calls": reply.tool_calls})
        for call in reply.tool_calls:
            result = self._tools.dispatch(call.name, call.arguments)
            evidence.append(result)
            tool_names.append(call.name)  # keep evidence and tool_names aligned
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": json.dumps(result)}
            )
        return self._llm.chat(messages, self._tools.schemas)

    def _fallback(self, question: str, evidence: list, tool_names: list[str]) -> ChatAnswer:
        """Deterministic answer: the data the model already fetched, or what the offline planner would fetch."""
        usable = [(name, data) for name, data in zip(tool_names, evidence) if "error" not in data]
        if not usable:  # nothing fetched yet, or only failed calls: let the offline planner choose
            call = StubClient().plan(question, self._tools.scheduled_labels())
            usable, tool_names = [
                (call.name, self._tools.dispatch(call.name, call.arguments))
            ], tool_names + [call.name]
        name, data = usable[-1]
        text = templates.answer_from_tool(name, data)
        return ChatAnswer(
            text=text,
            tool_names=tool_names,
            scenario=self._tools.last_scenario,
            used_fallback=True,
            proposals=self._tools.last_proposals,
        )


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return text.strip()
