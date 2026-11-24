from pathlib import Path

import pytest
from test_cards import CARD

from climate_chat.openrouter import ChatResult
from climate_chat.service.cards import AnswerCard
from climate_chat.service.evaluate import Case, Outcome, load_cases, render_report
from climate_chat.service.pipeline import PipelineResult, Trace


def test_load_cases_from_repo_file():
    cases = load_cases()
    assert len(cases) >= 12
    assert {c.expect for c in cases} == {"reply", "not_a_claim", "any"}
    assert all(c.platform in (None, "x", "youtube", "facebook") for c in cases)


def test_load_cases_rejects_bad_expect(tmp_path: Path):
    path = tmp_path / "cases.toml"
    path.write_text('[[case]]\ncomment = "x"\nexpect = "maybe"\nnote = "n"\n')
    with pytest.raises(ValueError, match="expect"):
        load_cases(path)


def outcome(**overrides):
    trace = Trace(claim="Solar doesn't work at night", card=AnswerCard.from_dict(CARD))
    trace.calls.append(
        ("classify", ChatResult("{}", "anthropic/claude-haiku-5.5", 300, 60, 0, 0.0001))
    )
    args = {
        "case": Case("lol solar", "reply", "x", "match", "casual"),
        "run": 1,
        "result": PipelineResult(
            "Solar made 7% in 2024.",
            [{"source_id": "24-0003", "title": "Ember", "url": "u", "pages": "3"}],
            "Oversimplification",
            False,
            "reply",
        ),
        "error": None,
        "trace": trace,
        "seconds": 7.9,
    }
    return Outcome(**{**args, **overrides})


def test_render_report_contains_reply_card_and_costs():
    report = render_report([outcome()])
    assert "lol solar" in report
    assert "Solar made 7% in 2024." in report
    assert "Storage covers the evening peak." in report  # the card, to check faithfulness
    assert "24-0003" in report
    assert "7.9 s" in report
    assert "$0.0001" in report


def test_render_report_flags_unexpected_outcome_and_overlength():
    long = PipelineResult("x" * 300, [], None, False, "reply")
    unexpected = outcome(case=Case("hi", "not_a_claim", "x", "match", "n"), result=long)
    report = render_report([unexpected])
    assert "UNEXPECTED" in report
    assert "OVER LENGTH" in report


def test_render_report_shows_errors():
    report = render_report([outcome(result=None, error="upstream_error")])
    assert "upstream_error" in report


def test_load_cases_with_context(tmp_path: Path):
    path = tmp_path / "cases.toml"
    path.write_text(
        '[[case]]\ncomment = "This"\nexpect = "reply"\nnote = "n"\n'
        'subject = "A video"\nthread = "CO2 is plant food"\n'
        '[[case]]\ncomment = "hi"\nexpect = "any"\nnote = "n"\n'
    )
    with_context, without = load_cases(path)
    assert (with_context.subject, with_context.thread) == ("A video", "CO2 is plant food")
    assert (without.subject, without.thread) == (None, None)


def test_repo_cases_include_context():
    cases = load_cases()
    assert any(c.subject for c in cases) and any(c.thread for c in cases)


def test_report_shows_context():
    o = outcome(
        case=Case("lol", "reply", "x", "match", "n", subject="Heat pump video", thread="Scam")
    )
    report = render_report([o])
    assert "Heat pump video" in report and "Scam" in report


def test_report_shows_failures():
    o = outcome(result=None, error="upstream_error")
    o.trace.failures.append(
        {"role": "reply", "problems": ["the reply uses the number 12"], "output": "{}"}
    )
    assert "the reply uses the number 12" in render_report([o])
