"""Reply evaluation: run eval/replies.toml end to end against dev and write a report to
build/reports/replies.md for a person to read.

    uv run python -m climate_chat.service.evaluate [--runs 2]

Calls the pipeline directly, so Turnstile and the rate limit don't apply. A second run
shows the cache: every claim answered in the first run should hit it.
"""

from __future__ import annotations

import argparse
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from climate_chat.config import repo_root
from climate_chat.service.api import PLATFORMS, STYLES, ApiError
from climate_chat.service.pipeline import PipelineResult, Trace
from climate_chat.service.prompts import reply_length

EXPECT = ("reply", "not_a_claim", "any")


@dataclass(frozen=True)
class Case:
    comment: str
    expect: str
    platform: str | None
    style: str
    note: str


@dataclass(frozen=True)
class Outcome:
    case: Case
    run: int
    result: PipelineResult | None
    error: str | None
    trace: Trace
    seconds: float


def cases_path() -> Path:
    return repo_root() / "eval" / "replies.toml"


def load_cases(path: Path | None = None) -> list[Case]:
    data = tomllib.loads((path or cases_path()).read_text())
    cases = []
    for n, entry in enumerate(data.get("case", []), start=1):
        expect = entry.get("expect")
        if expect not in EXPECT:
            raise ValueError(f"case {n}: expect must be one of {EXPECT}, got {expect!r}")
        platform, style = entry.get("platform"), entry.get("style", "match")
        if platform not in (None, *PLATFORMS) or style not in STYLES:
            raise ValueError(f"case {n}: bad platform or style")
        cases.append(Case(entry["comment"], expect, platform, style, entry.get("note", "")))
    return cases


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_report(outcomes: list[Outcome]) -> str:
    lines = ["# Reply evaluation", ""]
    rows = ["| # | Run | Outcome | Cached | Time | Cost | Flags |", "|---|---|---|---|---|---|---|"]
    details: list[str] = []
    total_cost = 0.0
    for n, o in enumerate(outcomes, 1):
        cost = sum(c.cost for _, c in o.trace.calls)
        total_cost += cost
        got = o.result.outcome if o.result else f"error:{o.error}"
        flags = []
        if o.case.expect != "any" and got != o.case.expect:
            flags.append("UNEXPECTED")
        limit = reply_length(o.case.platform)
        if o.result and o.result.outcome == "reply" and len(o.result.reply) > limit:
            flags.append("OVER LENGTH")
        rows.append(
            f"| {n} | {o.run} | {got} | {'yes' if o.trace.cached else 'no'} | "
            f"{o.seconds:.1f} s | ${cost:.4f} | {' '.join(flags)} |"
        )
        details += [
            f"## {n}. {_cell(o.case.note)} (run {o.run})",
            "",
            f"**Comment** ({o.case.platform or 'default'}, {o.case.style}, expect "
            f"{o.case.expect}): {o.case.comment}",
            "",
            f"**Claim:** {o.trace.claim or '-'}",
            "",
        ]
        if o.result:
            details += [
                f"**Reply** ({len(o.result.reply)}/{limit} chars, fallacy: "
                f"{o.result.fallacy or '-'}):",
                "",
                f"> {o.result.reply}",
                "",
                "**Citations:** "
                + (
                    "; ".join(
                        f"{c['source_id']} {c['title']} p{c['pages']}" for c in o.result.citations
                    )
                    or "-"
                ),
                "",
            ]
        else:
            details += [f"**Error:** {o.error}", ""]
        if o.trace.card:
            details.append("**Card key points:**")
            details += [
                f"- {kp.point} ({', '.join(kp.source_ids)})" for kp in o.trace.card.key_points
            ]
            details += [f"- Bottom line: {o.trace.card.bottom_line}", ""]
        calls = ", ".join(
            f"{role} {c.model.split('/')[-1]} {c.completion_tokens} out"
            + (f" ({c.reasoning_tokens} reasoning)" if c.reasoning_tokens else "")
            for role, c in o.trace.calls
        )
        details += [f"**Calls:** {calls or '-'}", ""]
    lines += [*rows, "", f"Total cost: ${total_cost:.4f}", "", *details]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval/replies.toml against dev.")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()

    from climate_chat.service.app import build_app

    pipeline = build_app().pipeline()
    outcomes = []
    for run in range(1, args.runs + 1):
        for case in load_cases():
            trace, start = Trace(), time.monotonic()
            result, error = None, None
            try:
                result = pipeline.run(case.comment, case.style, case.platform, trace)
            except ApiError as e:
                error = e.code
            outcomes.append(Outcome(case, run, result, error, trace, time.monotonic() - start))
            print(f"run {run}: {case.note[:50]:50} {result.outcome if result else error}")
    out = repo_root() / "build" / "reports" / "replies.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(outcomes))
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
