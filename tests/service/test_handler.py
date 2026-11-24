import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_secrets import ENV

from climate_chat.config import load_service_settings
from climate_chat.openrouter import ChatResult
from climate_chat.service.api import ApiError
from climate_chat.service.app import App
from climate_chat.service.pipeline import PipelineResult

NOW = datetime(2026, 11, 24, 14, 5, tzinfo=UTC)
RESULT = PipelineResult(
    "Solar made 7% of electricity in 2024.",
    [{"source_id": "24-0003", "title": "Ember", "url": "https://e.org", "pages": "3"}],
    "Oversimplification",
    False,
    "reply",
)


class FakePipeline:
    def __init__(self, result=RESULT, error=None):
        self.result, self.error, self.calls = result, error, []

    def run(self, comment, style, platform, trace, *, subject=None, thread=None):
        self.calls.append((comment, style, platform))
        self.context = (subject, thread)
        trace.claim = "Solar doesn't work at night"
        trace.calls.append(("classify", ChatResult("{}", "m", 10, 5, 0, 0.0001)))
        if self.error:
            raise self.error
        return self.result


class FakeSecrets:
    def __init__(self):
        self.key = "sk-1"

    def openrouter_key(self):
        return self.key

    def turnstile_secret(self):
        return "ts"

    def log_hash_key(self):
        return "hash-key"


class FakeRateLimiter:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def check(self, ip, now):
        self.calls.append(ip)
        if self.error:
            raise self.error


class FakeTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)


class Harness:
    def __init__(self, pipeline=None, turnstile_error=None, rate_error=None):
        self.pipeline = pipeline or FakePipeline()
        self.built_with = []
        self.verified = []
        self.secrets = FakeSecrets()
        self.rate = FakeRateLimiter(rate_error)
        self.table = FakeTable()

        def factory(key):
            self.built_with.append(key)
            return self.pipeline

        def verify(token, secret, ip):
            self.verified.append((token, secret, ip))
            if turnstile_error:
                raise turnstile_error

        settings = load_service_settings(environ=ENV, dotenv_path=Path("/none/.env"))
        self.app = App(
            settings=settings,
            secrets=self.secrets,
            pipeline_factory=factory,
            rate_limiter=self.rate,
            log_table=self.table,
            verify_turnstile=verify,
            now=lambda: NOW,
        )

    def call(self, event):
        return self.app.handle(event, None)


def url_event(body=None, method="POST", path="/api/chat", b64=False, headers=None):
    if body is not None and not isinstance(body, str):
        body = json.dumps(body)
    if b64 and body is not None:
        body = base64.b64encode(body.encode()).decode()
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method}, "requestId": "req-1"},
        "headers": headers or {"cloudfront-viewer-address": "203.0.113.9:443"},
        "body": body,
        "isBase64Encoded": b64,
    }


GOOD = {"comment": "lol solar is useless at night", "turnstile_token": "tok", "platform": "x"}


def payload(response):
    return json.loads(response["body"])


def test_chat_happy_path():
    h = Harness()
    response = h.call(url_event(GOOD))
    assert response["statusCode"] == 200
    assert payload(response) == {
        "reply": RESULT.reply,
        "citations": RESULT.citations,
        "fallacy": "Oversimplification",
        "cached": False,
    }
    assert h.pipeline.calls == [("lol solar is useless at night", "match", "x")]
    assert h.verified == [("tok", "ts", "203.0.113.9")]
    assert h.rate.calls == ["203.0.113.9"]


def test_chat_is_logged_with_user_hash_and_trace():
    h = Harness()
    h.call(url_event(GOOD))
    (item,) = h.table.items
    assert item["outcome"] == "reply"
    assert item["claim"] == "Solar doesn't work at night"
    assert len(item["user_hash"]) == 16
    assert item["sk"].endswith("#req-1")
    assert "203.0.113.9" not in json.dumps(item, default=str)


def test_base64_body_is_decoded():
    h = Harness()
    assert h.call(url_event(GOOD, b64=True))["statusCode"] == 200


@pytest.mark.parametrize(
    ("harness_kwargs", "event_body", "status"),
    [
        ({}, "not json", 400),
        ({}, {**GOOD, "comment": "a" * 1001}, 400),
        ({}, {"comment": "hi"}, 403),
        ({"turnstile_error": ApiError(403, "turnstile_failed", "no")}, GOOD, 403),
        ({"turnstile_error": ApiError(503, "unavailable", "down")}, GOOD, 503),
        ({"rate_error": ApiError(429, "rate_limited", "slow down")}, GOOD, 429),
    ],
)
def test_checks_run_before_any_llm_call(harness_kwargs, event_body, status):
    h = Harness(**harness_kwargs)
    response = h.call(url_event(event_body))
    assert response["statusCode"] == status
    assert h.pipeline.calls == []
    assert h.built_with == []
    (item,) = h.table.items
    assert item["outcome"].startswith("error:")


def test_length_cap_checked_before_turnstile():
    h = Harness()
    h.call(url_event({**GOOD, "comment": "a" * 1001}))
    assert h.verified == [] and h.rate.calls == []


def test_turnstile_before_rate_limit():
    h = Harness(turnstile_error=ApiError(403, "turnstile_failed", "no"))
    h.call(url_event(GOOD))
    assert h.rate.calls == []


def test_unknown_route_404():
    h = Harness()
    response = h.call(url_event(GOOD, path="/api/other"))
    assert response["statusCode"] == 404
    assert payload(response)["error"] == "not_found"
    assert h.table.items == []


def test_wrong_method_405():
    h = Harness()
    response = h.call(url_event(None, method="GET"))
    assert response["statusCode"] == 405
    assert h.table.items == []


def test_pipeline_error_is_returned_and_logged_with_trace():
    h = Harness(pipeline=FakePipeline(error=ApiError(502, "upstream_error", "x")))
    response = h.call(url_event(GOOD))
    assert response["statusCode"] == 502
    (item,) = h.table.items
    assert item["outcome"] == "error:upstream_error"
    assert item["claim"] == "Solar doesn't work at night"
    assert len(item["calls"]) == 1


def test_unexpected_error_is_500_and_logged(capsys):
    h = Harness(pipeline=FakePipeline(error=RuntimeError("secret detail")))
    response = h.call(url_event(GOOD))
    assert response["statusCode"] == 500
    assert payload(response)["error"] == "internal"
    assert "secret detail" not in response["body"]
    captured = capsys.readouterr()
    assert "secret detail" in captured.out + captured.err  # CloudWatch, not the reply
    assert h.table.items[0]["outcome"] == "error:internal"


def test_smoke_event_skips_turnstile_and_rate_limit():
    h = Harness()
    response = h.call({"smoke": "Solar is useless at night"})
    assert response["statusCode"] == 200
    assert payload(response)["reply"] == RESULT.reply
    assert h.verified == [] and h.rate.calls == []
    assert h.pipeline.calls == [("Solar is useless at night", "match", None)]
    assert h.table.items[0]["user_hash"] == "smoke"


def test_function_url_event_never_treated_as_smoke():
    h = Harness(turnstile_error=ApiError(403, "turnstile_failed", "no"))
    event = url_event({"smoke": "x", **GOOD})
    event["smoke"] = "injected at top level"
    response = h.call(event)
    assert response["statusCode"] == 403
    assert h.pipeline.calls == []


def test_unknown_event_is_400():
    h = Harness()
    assert h.call({"something": "else"})["statusCode"] == 400


def test_pipeline_rebuilt_only_when_key_rotates():
    h = Harness()
    h.call(url_event(GOOD))
    h.call(url_event(GOOD))
    h.secrets.key = "sk-2"
    h.call(url_event(GOOD))
    assert h.built_with == ["sk-1", "sk-2"]


def test_log_hash_key_failure_does_not_fail_request(capsys):
    h = Harness()

    def broken():
        raise RuntimeError("ParameterNotFound")

    h.secrets.log_hash_key = broken
    response = h.call(url_event(GOOD))
    assert response["statusCode"] == 200
    assert h.table.items[0]["user_hash"] == "unknown"
    assert "user_hash unavailable" in capsys.readouterr().out


# --- comment context (plan 05) ---


def test_chat_passes_context_and_logs_it():
    h = Harness()
    h.call(url_event({**GOOD, "subject": "Heat pump video", "thread": "They don't work"}))
    assert h.pipeline.context == ("Heat pump video", "They don't work")
    item = h.table.items[0]
    assert (item["subject"], item["thread"]) == ("Heat pump video", "They don't work")


def test_chat_without_context_passes_none():
    h = Harness()
    h.call(url_event(GOOD))
    assert h.pipeline.context == (None, None)
    assert "subject" not in h.table.items[0] and "thread" not in h.table.items[0]


def test_smoke_event_with_context():
    h = Harness()
    response = h.call({"smoke": "it fails in winter", "subject": "  Heat pump video  "})
    assert response["statusCode"] == 200
    assert h.pipeline.context == ("Heat pump video", None)
    assert h.table.items[0]["subject"] == "Heat pump video"


def test_smoke_event_over_long_context_is_400():
    h = Harness()
    response = h.call({"smoke": "x", "thread": "a" * 1001})
    assert response["statusCode"] == 400
    assert h.pipeline.calls == []


def test_over_long_thread_is_400_before_turnstile():
    h = Harness()
    response = h.call(url_event({**GOOD, "thread": "a" * 1001}))
    assert response["statusCode"] == 400
    assert json.loads(response["body"])["error"] == "thread_too_long"
    assert h.verified == [] and h.pipeline.calls == []


def test_context_caps_come_from_settings():
    from dataclasses import replace

    h = Harness()
    h.app.settings = replace(h.app.settings, max_subject_chars=5)
    response = h.call(url_event({**GOOD, "subject": "123456"}))
    assert json.loads(response["body"])["error"] == "subject_too_long"
