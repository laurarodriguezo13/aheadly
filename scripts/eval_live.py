"""Roadmap 5.4: ask the chat test set (tests/eval_questions.json) of the connected model, by hand.

CI asks the same questions of the offline chat; this checks the real model's choices and words with
the same checks (the right tool, every number from the tool results, at most 120 words, the words
each answer must and mustn't say). It uses LLM_PROVIDER and the key from .env, so it costs quota:
each question is 2-3 requests, and Gemini's free tier allows a limited number a day. Run it after
changing a prompt or a tool, and before the demo; at most a couple of times a day.

  uv run python -m scripts.eval_live                 # every question
  uv run python -m scripts.eval_live --only bakery   # questions whose id starts with "bakery"
  uv run python -m scripts.eval_live --pause 6       # seconds between questions (default 4)
"""

from __future__ import annotations

import argparse
import sys
import time

from aheadly.ai.llm_client import StubClient, create_llm_client
from aheadly.config import load_settings
from tests.chat_eval import business_core, load_questions, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="", help="only questions whose id starts with this")
    parser.add_argument("--pause", type=float, default=4.0, help="seconds between questions")
    args = parser.parse_args(argv)

    llm = create_llm_client(load_settings())
    if isinstance(llm, StubClient):
        print("LLM_PROVIDER is stub: set LLM_PROVIDER=gemini and GEMINI_API_KEY in .env first.")
        return 2
    questions = [q for q in load_questions() if q["id"].startswith(args.only)]
    cores: dict = {}
    passed, fallback, failed = 0, 0, []
    for n, item in enumerate(questions, 1):
        if item["business"] not in cores:
            cores[item["business"]] = business_core(item["business"])
            cores[item["business"]].translator._llm = llm  # the connected model, not the offline chat
        core = cores[item["business"]]
        core.clear_chat()
        answer = core.ask(item["question"])
        wrong = problems(item, answer)
        if answer.used_fallback:
            fallback += 1
            wrong.append("the model failed or invented a number: the offline answer was used")
        mark = "PASS" if not wrong else "FAIL"
        print(f"[{n}/{len(questions)}] {mark} {item['id']}: {item['question']}")
        print(f"    tools: {', '.join(answer.tool_names) or 'none'}")
        print("    " + answer.text.replace("\n", " ")[:400])
        for w in wrong:
            print(f"    - {w}")
        if wrong:
            failed.append(item["id"])
        else:
            passed += 1
        if n < len(questions):
            time.sleep(args.pause)
    print(f"\n{passed} of {len(questions)} passed; offline answer used {fallback} times.")
    if failed:
        print("Failed: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
