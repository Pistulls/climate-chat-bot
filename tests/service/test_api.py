import json

import pytest

from climate_chat.service.api import ApiError, ChatRequest, ok_response, parse_request

TOKEN = "XXXX.DUMMY.TOKEN.XXXX"


def body(**fields):
    return json.dumps({"comment": "Solar is useless at night", "turnstile_token": TOKEN, **fields})


def parse(text, max_chars=1000):
    return parse_request(text, max_chars=max_chars)


def error_of(text, max_chars=1000):
    with pytest.raises(ApiError) as info:
        parse(text, max_chars)
    return info.value


def test_parse_valid_request():
    req = parse(body(platform="x", style="neutral"))
    assert req == ChatRequest(
        comment="Solar is useless at night", turnstile_token=TOKEN, platform="x", style="neutral"
    )


def test_parse_defaults_style_match():
    req = parse(body())
    assert (req.style, req.platform) == ("match", None)


def test_parse_strips_comment_whitespace():
    assert parse(body(comment="  hi there \n")).comment == "hi there"


@pytest.mark.parametrize("text", [None, "", "not json", "[1, 2]", '"a string"'])
def test_parse_rejects_bad_json(text):
    err = error_of(text)
    assert (err.status, err.code) == (400, "bad_request")


def test_parse_rejects_unknown_style():
    err = error_of(body(style="sarcastic"))
    assert (err.status, err.code) == (400, "bad_request")
    assert "style" in err.message


def test_parse_rejects_unknown_platform():
    err = error_of(body(platform="tiktok"))
    assert (err.status, err.code) == (400, "bad_request")
    assert "platform" in err.message


@pytest.mark.parametrize("comment", ["", "   \n", None, 42])
def test_parse_rejects_blank_or_non_string_comment(comment):
    err = error_of(body(comment=comment))
    assert (err.status, err.code) == (400, "bad_request")


def test_length_cap_counts_characters():
    assert parse(body(comment="🌍" * 1000)).comment == "🌍" * 1000
    assert parse(body(comment="é" * 1000)).comment == "é" * 1000
    err = error_of(body(comment="a" * 1001))
    assert (err.status, err.code) == (400, "comment_too_long")


def test_length_cap_checked_before_token():
    err = error_of(json.dumps({"comment": "a" * 1001}))
    assert err.code == "comment_too_long"


@pytest.mark.parametrize("token", [None, "", 7])
def test_missing_token_is_403(token):
    fields = {"comment": "Solar is useless at night"}
    if token is not None:
        fields["turnstile_token"] = token
    err = error_of(json.dumps(fields))
    assert (err.status, err.code) == (403, "turnstile_failed")


def test_api_error_to_response():
    response = ApiError(429, "rate_limited", "Too many requests").to_response()
    assert response["statusCode"] == 429
    assert response["headers"]["content-type"] == "application/json"
    assert json.loads(response["body"]) == {
        "error": "rate_limited",
        "message": "Too many requests",
    }


def test_ok_response():
    response = ok_response({"reply": "r", "citations": [], "fallacy": None, "cached": False})
    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "application/json"
    assert json.loads(response["body"])["reply"] == "r"


def test_length_cap_counts_decomposed_accents_once():
    decomposed = "é" * 1000  # "é" typed as e + combining accent
    assert len(parse(body(comment=decomposed)).comment) == 1000


# --- subject and thread (plan 05) ---


def test_parse_subject_and_thread():
    req = parse(body(subject="  YouTube: heat pumps in a UK semi ", thread="Heat pumps are a scam"))
    assert req.subject == "YouTube: heat pumps in a UK semi"
    assert req.thread == "Heat pumps are a scam"


def test_context_absent_is_none():
    req = parse(body())
    assert (req.subject, req.thread) == (None, None)


@pytest.mark.parametrize("blank", ["", "   \n", None])
def test_blank_context_is_none(blank):
    req = parse(body(subject=blank, thread=blank))
    assert (req.subject, req.thread) == (None, None)


@pytest.mark.parametrize("field", ["subject", "thread"])
@pytest.mark.parametrize("value", [42, ["a"], {"a": 1}, True])
def test_context_must_be_string(field, value):
    err = error_of(body(**{field: value}))
    assert (err.status, err.code) == (400, "bad_request")
    assert field in err.message


def test_subject_cap_counts_characters():
    assert parse(body(subject="🌍" * 300)).subject == "🌍" * 300
    assert parse(body(subject="é" * 300)).subject == "é" * 300
    err = error_of(body(subject="a" * 301))
    assert (err.status, err.code) == (400, "subject_too_long")


def test_thread_cap():
    assert parse(body(thread="a" * 1000)).thread == "a" * 1000
    err = error_of(body(thread="a" * 1001))
    assert (err.status, err.code) == (400, "thread_too_long")


def test_context_caps_are_parameters():
    assert parse(body(subject="a" * 11)).subject == "a" * 11  # the default cap allows it
    with pytest.raises(ApiError) as info:
        parse_request(body(subject="a" * 11), max_chars=1000, max_subject_chars=10)
    assert info.value.code == "subject_too_long"


def test_context_caps_checked_before_token():
    err = error_of(json.dumps({"comment": "hi", "thread": "a" * 1001}))
    assert err.code == "thread_too_long"
