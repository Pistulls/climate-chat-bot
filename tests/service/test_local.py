from climate_chat.service.local import to_event


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
