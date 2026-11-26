from datetime import date
from types import SimpleNamespace

from fakes import FakeLogTable

from climate_chat.service.local import LOGS_PAGE_MAX, serve_logs, to_event

TODAY = date(2026, 11, 26)


def test_to_event_matches_function_url_shape():
    event = to_event("POST", "/api/chat?x=1", {"Content-Type": "application/json"}, b'{"a": 1}')
    assert event["rawPath"] == "/api/chat"
    assert event["requestContext"]["http"]["method"] == "POST"
    assert event["requestContext"]["requestId"]
    assert event["headers"] == {"content-type": "application/json"}
    assert event["body"] == '{"a": 1}'
    assert event["isBase64Encoded"] is False


def test_to_event_empty_body_is_none():
    assert to_event("GET", "/api/chat", {}, b"")["body"] is None


def logs_app(items=()):
    return SimpleNamespace(
        log_table=FakeLogTable(list(items)),
        settings=SimpleNamespace(log_ttl_days=90, logs_table="climate-chat-dev-logs"),
    )


def test_serve_logs_returns_a_page_and_the_table_name():
    app = logs_app([{"pk": "day#2026-11-26", "sk": "2026-11-26T10:00:00.000Z#a", "comment": "hi"}])
    status, body = serve_logs(app, "limit=10", TODAY)
    assert status == 200
    assert body["table"] == "climate-chat-dev-logs"
    assert [i["request_id"] for i in body["items"]] == ["a"]


def test_serve_logs_caps_the_page_size():
    app = logs_app()
    serve_logs(app, "limit=100000", TODAY)
    assert app.log_table.queries[0]["Limit"] == LOGS_PAGE_MAX


def test_serve_logs_explains_a_failed_read():
    class ExpiredTable:
        def query(self, **kwargs):
            raise RuntimeError("Token has expired and refresh failed")

    app = logs_app()
    app.log_table = ExpiredTable()
    status, body = serve_logs(app, "", TODAY)
    assert (status, body["error"]) == (503, "logs_unavailable")
    assert "climate-chat-dev-logs" in body["message"]
    assert "aws sso login" in body["message"]


def test_serve_logs_rejects_bad_input():
    assert serve_logs(logs_app(), "limit=ten", TODAY)[0] == 400
    status, body = serve_logs(logs_app(), "cursor=nonsense!", TODAY)
    assert (status, body["error"]) == (400, "bad_cursor")
