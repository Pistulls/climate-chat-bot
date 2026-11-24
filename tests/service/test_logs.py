from datetime import UTC, datetime
from decimal import Decimal

from botocore.exceptions import ClientError

from climate_chat.openrouter import ChatResult
from climate_chat.service.logs import log_item, write_log
from climate_chat.service.pipeline import PipelineResult, Trace

NOW = datetime(2026, 11, 24, 14, 5, 30, 123000, tzinfo=UTC)


def trace():
    t = Trace(claim="Solar doesn't work at night", cards_category="solutions_wont_work")
    t.calls.append(
        ("classify", ChatResult("{}", "anthropic/claude-haiku-5.5", 300, 60, 0, 0.00006))
    )
    t.calls.append(("reply", ChatResult("{}", "openai/gpt-6-luna", 800, 120, 0, 0.00014)))
    return t


def item(**overrides):
    args = {
        "comment": "lol solar is useless at night",
        "user_hash": "0123456789abcdef",
        "trace": trace(),
        "result": PipelineResult("reply text", [], "Oversimplification", False, "reply"),
        "error_code": None,
        "latency_ms": 3120,
        "now": NOW,
        "ttl_days": 90,
        "request_id": "req-1",
    }
    return log_item(**{**args, **overrides})


def test_log_item_fields():
    entry = item()
    assert entry["pk"] == "day#2026-11-24"
    assert entry["sk"] == "2026-11-24T14:05:30.123Z#req-1"
    assert entry["comment"] == "lol solar is useless at night"
    assert entry["user_hash"] == "0123456789abcdef"
    assert entry["claim"] == "Solar doesn't work at night"
    assert entry["cards_category"] == "solutions_wont_work"
    assert entry["cached"] is False
    assert entry["outcome"] == "reply"
    assert entry["latency_ms"] == 3120
    assert entry["calls"] == [
        {
            "role": "classify",
            "model": "anthropic/claude-haiku-5.5",
            "prompt_tokens": 300,
            "completion_tokens": 60,
            "reasoning_tokens": 0,
            "cost": Decimal("0.00006"),
        },
        {
            "role": "reply",
            "model": "openai/gpt-6-luna",
            "prompt_tokens": 800,
            "completion_tokens": 120,
            "reasoning_tokens": 0,
            "cost": Decimal("0.00014"),
        },
    ]
    assert entry["cost"] == Decimal("0.0002")


def test_log_item_error_outcome():
    entry = item(result=None, error_code="upstream_error")
    assert entry["outcome"] == "error:upstream_error"


def test_log_item_before_pipeline_has_no_claim():
    entry = item(result=None, error_code="rate_limited", trace=Trace())
    assert entry["outcome"] == "error:rate_limited"
    assert "claim" not in entry and entry["calls"] == [] and entry["cost"] == 0


def test_log_item_has_no_ip():
    entry = item(comment="hi")
    assert not any(k == "ip" or k.endswith("_ip") for k in entry)
    assert "203.0.113" not in str(entry)


def test_log_item_ttl():
    entry = item(ttl_days=90)
    assert entry["expires_at"] == int(datetime(2027, 2, 22, 14, 5, 30, tzinfo=UTC).timestamp())


def test_write_log_puts_item():
    class FakeTable:
        def __init__(self):
            self.items = []

        def put_item(self, Item):
            self.items.append(Item)

    table = FakeTable()
    write_log(table, {"pk": "a", "sk": "b"})
    assert table.items == [{"pk": "a", "sk": "b"}]


def test_write_log_failure_does_not_raise(capsys):
    class Broken:
        def put_item(self, Item):
            raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "PutItem")

    write_log(Broken(), {"pk": "a", "sk": "b"})
    assert "log write failed" in capsys.readouterr().out


def test_log_item_includes_failures():
    t = trace()
    t.failures.append({"role": "reply", "problems": ["too long"], "output": "{...}"})
    entry = item(trace=t, result=None, error_code="upstream_error")
    assert entry["failures"] == [{"role": "reply", "problems": ["too long"], "output": "{...}"}]


def test_log_item_omits_empty_failures():
    assert "failures" not in item()


def test_log_item_keeps_context():
    entry = item(subject="Heat pump video", thread="They don't work")
    assert (entry["subject"], entry["thread"]) == ("Heat pump video", "They don't work")


def test_log_item_omits_missing_context():
    entry = item()
    assert "subject" not in entry and "thread" not in entry
