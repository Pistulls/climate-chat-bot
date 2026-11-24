"""Run one comment through the real pipeline against dev and print every step.

    uv run python scripts/try_chat.py "Solar is useless at night lol"
    uv run python scripts/try_chat.py "..." --platform x --style neutral
    uv run python scripts/try_chat.py "mine barely works below 5C" \
        --subject "YouTube: our heat pump after one UK winter" --thread "..."
    uv run python scripts/try_chat.py "..." --prompts      # also print the messages sent
    uv run python scripts/try_chat.py "..." --use-cache    # read/write the dev response cache

By default the cache is bypassed (no read, no write), so Facts always runs and prompt
changes in src/climate_chat/service/prompts.py show up straight away. Uses .env (dev key).
"""

import argparse
import json

from climate_chat.service.api import ApiError
from climate_chat.service.app import build_app
from climate_chat.service.pipeline import Trace


class NoCache:
    def get(self, vector):
        return None

    def put(self, vector, card, sources):
        pass


class Recorder:
    """Wraps the chat client to keep each call's messages and raw output."""

    def __init__(self, chat):
        self.chat, self.log = chat, []

    def complete(self, model, messages, **kwargs):
        result = self.chat.complete(model, messages, **kwargs)
        self.log.append((messages, result))
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("comment")
    parser.add_argument("--platform", choices=["x", "youtube", "facebook"])
    parser.add_argument("--style", choices=["match", "neutral"], default="match")
    parser.add_argument("--subject", help="what the comment is under, e.g. a video title")
    parser.add_argument("--thread", help="the message the comment replies to")
    parser.add_argument("--prompts", action="store_true", help="print the messages sent")
    parser.add_argument("--use-cache", action="store_true", help="use the dev response cache")
    args = parser.parse_args()

    pipeline = build_app().pipeline()
    pipeline.chat = recorder = Recorder(pipeline.chat)
    if not args.use_cache:
        pipeline.cache = NoCache()

    trace = Trace()
    try:
        result = pipeline.run(
            args.comment,
            args.style,
            args.platform,
            trace,
            subject=args.subject or None,
            thread=args.thread or None,
        )
    except ApiError as e:
        result = None
        print(f"\n!! {e.status} {e.code}: {e.message}")

    print(f"\n=== CLAIM: {trace.claim or '(not a sceptical claim)'}")
    for (role, call), (messages, _) in zip(trace.calls, recorder.log, strict=True):
        print(
            f"\n=== {role} ({call.model}, {call.prompt_tokens} in / "
            f"{call.completion_tokens} out, ${call.cost:.5f})"
        )
        if args.prompts:
            for m in messages:
                print(f"--- {m['role']} ---\n{m['content']}")
            print("--- output ---")
        try:
            print(json.dumps(json.loads(call.text), indent=2, ensure_ascii=False))
        except ValueError:
            print(call.text or "(empty)")

    for f in trace.failures:
        print(f"\n!! {f['role']} failed: {'; '.join(f['problems'])}")
    if result:
        print(
            f"\n=== RESULT ({result.outcome}, cached={result.cached}, "
            f"{len(result.reply)} chars, fallacy: {result.fallacy})\n{result.reply}"
        )
        for c in result.citations:
            print(f"  [{c['source_id']}] {c['title']}, p{c['pages']}  {c['url']}")
    print(f"\nTotal ${sum(c.cost for _, c in trace.calls):.5f}")


if __name__ == "__main__":
    main()
